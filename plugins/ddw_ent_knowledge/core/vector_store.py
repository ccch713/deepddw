"""向量存储：SQLite + JSON embedding + 内存 cosine 搜索。"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class VectorStore:
    """基于 SQLite 的轻量向量存储，支持 tenant 隔离。"""

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
            c.execute("CREATE INDEX IF NOT EXISTS idx_kb_chunks_tenant ON chunks(tenant_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_kb_chunks_doc ON chunks(doc_id)")

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._db_path)
        c.row_factory = sqlite3.Row
        return c

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

    def search(
        self,
        tenant_id: int,
        query_embedding: List[float],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
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


__all__ = ["VectorStore"]
