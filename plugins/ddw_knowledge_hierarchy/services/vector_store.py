"""向量存储：基于 SQLite 的轻量实现（生产可替换为 pgvector）。

- 存储 chunks + embedding（JSON 数组）
- 检索：内存 cosine 相似度
- 适合 1-10 万 chunks 规模
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


class VectorStore:
    """基于 SQLite 的轻量向量存储。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._lock = threading.Lock()
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS kh_vector_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id INTEGER NOT NULL DEFAULT 0,
                    doc_id TEXT NOT NULL,
                    chunk_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    metadata_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_vkh_tenant ON kh_vector_chunks(tenant_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_vkh_doc ON kh_vector_chunks(doc_id)")

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._db_path)
        c.row_factory = sqlite3.Row
        return c

    def add(
        self,
        tenant_id: int,
        doc_id: str,
        chunk_ids: List[str],
        contents: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        if metadatas is None:
            metadatas = [{}] * len(contents)
        with self._lock, self._conn() as c:
            for cid, content, emb, meta in zip(chunk_ids, contents, embeddings, metadatas):
                c.execute(
                    "INSERT INTO kh_vector_chunks(tenant_id, doc_id, chunk_id, content, embedding_json, metadata_json) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (tenant_id, doc_id, cid, content,
                     json.dumps(emb, ensure_ascii=False),
                     json.dumps(meta, ensure_ascii=False)),
                )

    def search(
        self,
        tenant_id: int,
        query_embedding: List[float],
        top_k: int = 10,
        doc_ids: Optional[List[str]] = None,
        score_threshold: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """余弦相似度检索（内存计算）。"""
        with self._lock, self._conn() as c:
            if doc_ids:
                placeholders = ",".join("?" * len(doc_ids))
                rows = c.execute(
                    f"SELECT * FROM kh_vector_chunks WHERE tenant_id=? AND doc_id IN ({placeholders})",
                    [tenant_id] + doc_ids,
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM kh_vector_chunks WHERE tenant_id=?",
                    (tenant_id,),
                ).fetchall()

        results: List[Dict[str, Any]] = []
        for row in rows:
            emb = json.loads(row["embedding_json"])
            score = self._cosine(query_embedding, emb)
            if score >= score_threshold:
                results.append({
                    "chunk_id": row["chunk_id"],
                    "doc_id": row["doc_id"],
                    "content": row["content"],
                    "score": round(score, 4),
                    "metadata": json.loads(row["metadata_json"] or "{}"),
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def delete_by_doc(self, tenant_id: int, doc_id: str) -> int:
        with self._lock, self._conn() as c:
            cur = c.execute(
                "DELETE FROM kh_vector_chunks WHERE tenant_id=? AND doc_id=?",
                (tenant_id, doc_id),
            )
            return cur.rowcount

    def count(self, tenant_id: int) -> int:
        with self._lock, self._conn() as c:
            row = c.execute(
                "SELECT COUNT(*) as cnt FROM kh_vector_chunks WHERE tenant_id=?",
                (tenant_id,),
            ).fetchone()
            return row["cnt"] if row else 0

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)
