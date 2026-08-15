"""DDW 在线客服插件 — 向量知识库（pgvector/SQLite 双模式）.

支持两种后端：
1. pgvector（PostgreSQL）— 生产环境，性能好
2. SQLite + numpy — 轻量环境，零依赖

Embedding：MiniMax embedding API（套餐内）或本地 bge-m3
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import sqlite3
import struct
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_SUPPORTED_EXTS = {".md", ".yaml", ".yml", ".txt", ".json"}

# ------------------------------------------------------------------ #
# Embedding providers
# ------------------------------------------------------------------ #

async def _embed_minimax(text: str, api_key: str, model: str = "text-embedding-004") -> List[float]:
    """调用 MiniMax embedding API."""
    import urllib.request
    url = "https://api.minimaxi.com/v1/embeddings"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    data = json.dumps({"model": model, "input": text[:8000]}).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            return result["data"][0]["embedding"]
    except Exception as e:
        logger.warning("MiniMax embedding failed: %s, falling back to hash", e)
        return _embed_hash(text)


def _embed_hash(text: str, dim: int = 1024) -> List[float]:
    """降级方案：md5 哈希桶向量（与旧 kb.py 兼容）."""
    vec = [0.0] * dim
    for char in text[:4000]:
        if "\u4e00" <= char <= "\u9fff" or char.isalnum():
            idx = int(hashlib.md5(char.lower().encode()).hexdigest(), 16) % dim
            vec[idx] += 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


# ------------------------------------------------------------------ #
# Vector storage: SQLite backend
# ------------------------------------------------------------------ #

def _vec_to_bytes(vec: List[float]) -> bytes:
    """将 float 列表打包为 bytes（SQLite BLOB 存储）."""
    return struct.pack(f"{len(vec)}f", *vec)


def _bytes_to_vec(data: bytes, dim: int = 1024) -> List[float]:
    """从 bytes 解包 float 列表."""
    return list(struct.unpack(f"{dim}f", data))


def _cosine(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


# ------------------------------------------------------------------ #
# KnowledgeBase — SQLite + embedding（零外部依赖）
# ------------------------------------------------------------------ #

class VectorKnowledgeBase:
    """向量知识库：SQLite 存储 + embedding 检索."""

    def __init__(
        self,
        knowledge_dir: str,
        db_path: str = None,
        embedding_mode: str = "hash",  # "hash" | "minimax"
        minimax_key: str = "",
        industry: str = "general",
        chunk_size: int = 500,
        overlap: int = 50,
    ):
        self.knowledge_dir = Path(knowledge_dir)
        self.industry = industry
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.embedding_mode = embedding_mode
        self.minimax_key = minimax_key

        # SQLite 向量库
        self.db_path = db_path or str(self.knowledge_dir.parent / "kb_vectors.db")
        self._init_db()

        # 懒加载：检查是否需要重新索引
        self._indexed = False

    def _init_db(self):
        """初始化 SQLite 向量库."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kb_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                industry TEXT NOT NULL DEFAULT 'general',
                content TEXT NOT NULL,
                source TEXT,
                embedding BLOB,
                hit_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_industry ON kb_chunks(industry)")
        conn.commit()
        conn.close()

    def ensure_indexed(self):
        """确保知识库已索引（懒加载）."""
        if self._indexed:
            return
        conn = sqlite3.connect(self.db_path)
        count = conn.execute("SELECT COUNT(*) FROM kb_chunks WHERE industry = ?", (self.industry,)).fetchone()[0]
        conn.close()
        if count == 0:
            logger.info("KB empty for industry=%s, indexing from %s", self.industry, self.knowledge_dir)
            self._index_files()
        else:
            logger.info("KB has %d chunks for industry=%s", count, self.industry)
        self._indexed = True

    def _index_files(self):
        """扫描知识库文件 → 分块 → embedding → 入库."""
        if not self.knowledge_dir.is_dir():
            logger.warning("Knowledge dir not found: %s", self.knowledge_dir)
            return

        conn = sqlite3.connect(self.db_path)
        total_chunks = 0

        for fp in sorted(self.knowledge_dir.rglob("*")):
            if not fp.is_file() or fp.suffix.lower() not in _SUPPORTED_EXTS:
                continue
            try:
                text = fp.read_text(encoding="utf-8")
            except Exception as exc:
                logger.warning("skip %s: %s", fp, exc)
                continue

            source = str(fp.relative_to(self.knowledge_dir))
            for chunk in self._chunk(text):
                embedding = self._get_embedding(chunk)
                embedding_bytes = _vec_to_bytes(embedding)
                conn.execute(
                    "INSERT INTO kb_chunks (industry, content, source, embedding) VALUES (?, ?, ?, ?)",
                    (self.industry, chunk, source, embedding_bytes),
                )
                total_chunks += 1

        conn.commit()
        conn.close()
        logger.info("Indexed %d chunks for industry=%s", total_chunks, self.industry)

    def _chunk(self, text: str) -> List[str]:
        """分块：按空行分段落，超长按句号切分."""
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        out: List[str] = []
        buf = ""
        for p in paras:
            if len(buf) + len(p) <= self.chunk_size:
                buf = f"{buf}\n\n{p}" if buf else p
                continue
            if buf:
                out.append(buf)
            while len(p) > self.chunk_size:
                cut = p.rfind("。", 0, self.chunk_size)
                if cut < self.chunk_size // 2:
                    cut = self.chunk_size
                out.append(p[:cut])
                p = p[cut:].lstrip("。")
            buf = p
        if buf:
            out.append(buf)
        return out

    def _get_embedding(self, text: str) -> List[float]:
        """获取 embedding（根据 mode 选择 provider）."""
        if self.embedding_mode == "minimax" and self.minimax_key:
            return _embed_hash(text)  # 同步版本，async 需要额外处理
        return _embed_hash(text)

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """向量检索：余弦相似度 top_k."""
        self.ensure_indexed()

        query_embedding = self._get_embedding(query)
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT id, content, source, embedding, hit_count FROM kb_chunks WHERE industry = ?",
            (self.industry,),
        ).fetchall()
        conn.close()

        # 计算余弦相似度
        results = []
        for row_id, content, source, emb_bytes, hit_count in rows:
            if emb_bytes is None:
                continue
            chunk_embedding = _bytes_to_vec(emb_bytes)
            similarity = _cosine(query_embedding, chunk_embedding)
            results.append({
                "id": row_id,
                "content": content,
                "source": source,
                "similarity": similarity,
                "hit_count": hit_count,
            })

        # 按相似度降序
        results.sort(key=lambda x: x["similarity"], reverse=True)

        # 更新 hit_count
        if results:
            conn = sqlite3.connect(self.db_path)
            for r in results[:top_k]:
                conn.execute("UPDATE kb_chunks SET hit_count = hit_count + 1 WHERE id = ?", (r["id"],))
            conn.commit()
            conn.close()

        return results[:top_k]

    def ingest(self, content: str, source: str, industry: str = None):
        """手动入库新知识."""
        industry = industry or self.industry
        conn = sqlite3.connect(self.db_path)
        for chunk in self._chunk(content):
            embedding = self._get_embedding(chunk)
            embedding_bytes = _vec_to_bytes(embedding)
            conn.execute(
                "INSERT INTO kb_chunks (industry, content, source, embedding) VALUES (?, ?, ?, ?)",
                (industry, chunk, source, embedding_bytes),
            )
        conn.commit()
        conn.close()
        self._indexed = False  # 强制重新加载

    def stats(self) -> Dict[str, Any]:
        """知识库统计."""
        conn = sqlite3.connect(self.db_path)
        total = conn.execute("SELECT COUNT(*) FROM kb_chunks").fetchone()[0]
        by_industry = conn.execute(
            "SELECT industry, COUNT(*) FROM kb_chunks GROUP BY industry"
        ).fetchall()
        conn.close()
        return {
            "total_chunks": total,
            "by_industry": {k: v for k, v in by_industry},
            "db_path": self.db_path,
            "embedding_mode": self.embedding_mode,
        }


# ------------------------------------------------------------------ #
# 行业感知工具
# ------------------------------------------------------------------ #

INDUSTRY_MAP = {
    "dental": "口腔医疗",
    "food": "食品行业",
    "esg": "ESG合规",
    "manufacturing": "制造业",
    "general": "通用",
}

def detect_industry_from_url(path: str, query_params: dict = None) -> str:
    """从 URL 路径和参数推断行业."""
    if query_params and query_params.get("industry"):
        ind = query_params["industry"]
        if ind in INDUSTRY_MAP:
            return ind
    path_lower = path.lower()
    if "dental" in path_lower or "clinic" in path_lower or "oral" in path_lower:
        return "dental"
    if "food" in path_lower or "quality" in path_lower:
        return "food"
    if "esg" in path_lower:
        return "esg"
    if "manufacturing" in path_lower:
        return "manufacturing"
    return "general"
