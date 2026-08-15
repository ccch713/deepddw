"""向量存储：基于 SQLite 的轻量实现。

- 存储 chunks + embedding（JSON 数组）
- 检索：内存 cosine 相似度
- 适合 1-10 万 chunks 规模
- 真实部署可替换为 chroma / lancedb / milvus
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from plugins.ddw_bid_writer.services.embedding_service import (
    EmbeddingService,
    get_default_embedding,
)

logger = logging.getLogger(__name__)


class VectorStore:
    """基于 SQLite 的轻量向量存储。

    表结构：
    - chunks(id, tenant_id, doc_id, content, embedding_json, metadata_json)
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._lock = threading.Lock()
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id INTEGER NOT NULL,
                    doc_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    metadata_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            c.execute("CREATE INDEX IF NOT EXISTS idx_chunks_tenant ON chunks(tenant_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id)")

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._db_path)
        c.row_factory = sqlite3.Row
        return c

    # ----------------- 写入 ----------------- #

    def add(
        self,
        tenant_id: int,
        doc_id: str,
        contents: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> List[int]:
        assert len(contents) == len(embeddings)
        if metadatas is None:
            metadatas = [{}] * len(contents)
        ids: List[int] = []
        with self._lock, self._conn() as c:
            for content, emb, meta in zip(contents, embeddings, metadatas):
                cur = c.execute(
                    "INSERT INTO chunks(tenant_id, doc_id, content, embedding_json, metadata_json) VALUES (?, ?, ?, ?, ?)",
                    (tenant_id, doc_id, content, json.dumps(emb, ensure_ascii=False), json.dumps(meta, ensure_ascii=False)),
                )
                ids.append(cur.lastrowid)
            c.commit()
        return ids

    def delete_by_doc(self, tenant_id: int, doc_id: str) -> int:
        with self._lock, self._conn() as c:
            cur = c.execute(
                "DELETE FROM chunks WHERE tenant_id = ? AND doc_id = ?", (tenant_id, doc_id)
            )
            c.commit()
            return cur.rowcount

    def count(self, tenant_id: int) -> int:
        with self._conn() as c:
            r = c.execute("SELECT COUNT(*) AS n FROM chunks WHERE tenant_id = ?", (tenant_id,)).fetchone()
            return int(r["n"] or 0)

    # ----------------- 检索 ----------------- #

    def search(
        self,
        tenant_id: int,
        query_embedding: List[float],
        top_k: int = 5,
        filter_doc_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """返回 top_k 相似 chunks，按 cosine 相似度降序。"""
        rows = self._fetch_all(tenant_id)
        if not rows:
            return []
        scored: List[Tuple[float, Dict[str, Any]]] = []
        for row in rows:
            try:
                emb = json.loads(row["embedding_json"])
            except (json.JSONDecodeError, TypeError):
                continue
            score = _cosine(query_embedding, emb)
            meta = {}
            try:
                meta = json.loads(row["metadata_json"] or "{}")
            except (json.JSONDecodeError, TypeError):
                pass
            if filter_doc_type and meta.get("doc_type") != filter_doc_type:
                continue
            scored.append((score, {
                "id": row["id"],
                "doc_id": row["doc_id"],
                "content": row["content"],
                "metadata": meta,
                "score": round(float(score), 4),
            }))
        scored.sort(key=lambda x: -x[0])
        return [item for _, item in scored[:top_k]]

    def _fetch_all(self, tenant_id: int) -> List[sqlite3.Row]:
        with self._conn() as c:
            return list(
                c.execute(
                    "SELECT id, doc_id, content, embedding_json, metadata_json FROM chunks WHERE tenant_id = ?",
                    (tenant_id,),
                ).fetchall()
            )


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ----------------- 高层封装（用于 knowledge_bootstrap） ----------------- #


class TenantKnowledgeStore:
    """租户级知识库封装。"""

    def __init__(self, tenant_id: int, base_dir: str = "./data/bid_kb") -> None:
        self.tenant_id = tenant_id
        kb_dir = Path(base_dir) / f"tenant_{tenant_id}"
        kb_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = kb_dir / "vectors.sqlite"
        self.embedding: EmbeddingService = get_default_embedding()
        self.store = VectorStore(self.db_path)

    def add_document(
        self, doc_id: str, chunks: List[str], metadatas: Optional[List[Dict[str, Any]]] = None
    ) -> List[int]:
        """同步添加文档到向量库。用于非 async 上下文。"""
        if chunks:
            if hasattr(self.embedding, "fit_idf"):
                self.embedding.fit_idf(chunks)
            # 同步计算 embedding（直接调内部方法，跳过 async 包装）
            embeddings: List[List[float]] = []
            if hasattr(self.embedding, "_embed_from_tokens"):
                from plugins.ddw_bid_writer.services.embedding_service import _tokenize

                for c in chunks:
                    toks = _tokenize(c)
                    embeddings.append(self.embedding._embed_from_tokens(toks))
            else:
                # 退化：尝试 asyncio.run（仅在非 async 上下文）
                import asyncio

                for c in chunks:
                    embeddings.append(asyncio.run(self.embedding.embed(c)))
            return self.store.add(self.tenant_id, doc_id, chunks, embeddings, metadatas)
        return []

    async def add_document_async(
        self, doc_id: str, chunks: List[str], metadatas: Optional[List[Dict[str, Any]]] = None
    ) -> List[int]:
        """异步添加文档到向量库。用于 async 上下文。"""
        if chunks:
            if hasattr(self.embedding, "fit_idf"):
                self.embedding.fit_idf(chunks)
            embeddings = await self.embedding.embed_batch(chunks)
            return self.store.add(self.tenant_id, doc_id, chunks, embeddings, metadatas)
        return []

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filter_doc_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        q_emb = await self.embedding.embed(query)
        return self.store.search(self.tenant_id, q_emb, top_k=top_k, filter_doc_type=filter_doc_type)

    def stats(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "chunks": self.store.count(self.tenant_id),
            "embedding": self.embedding.name,
            "dim": self.embedding.dim(),
        }


__all__ = ["TenantKnowledgeStore", "VectorStore"]
