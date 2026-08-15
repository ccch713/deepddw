"""检索服务：向量 cosine top-k + BM25-lite 关键词 fallback。"""

from __future__ import annotations

import logging
import math
import re
import time
from collections import Counter
from typing import Any, Dict, List

from plugins.ddw_ent_knowledge.core.embedding import EmbeddingService
from plugins.ddw_ent_knowledge.core.vector_store import VectorStore

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fa5]{2,}", re.IGNORECASE)


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _bm25_score(query_tokens: List[str], doc_tokens: List[str], avg_dl: float, k1: float = 1.5, b: float = 0.75) -> float:
    """简化的 BM25 评分（单文档 vs query）。"""
    if not doc_tokens:
        return 0.0
    dl = len(doc_tokens)
    tf = Counter(doc_tokens)
    score = 0.0
    for qt in query_tokens:
        if qt in tf:
            term_freq = tf[qt]
            # 简化 IDF: 假设总文档数=1000, 包含该词的文档数=10 (偏保守)
            idf = math.log(1000 / 10) + 1.0
            numerator = term_freq * (k1 + 1)
            denominator = term_freq + k1 * (1 - b + b * dl / avg_dl)
            score += idf * numerator / denominator
    return score


class RetrievalService:
    """向量检索 + BM25-lite fallback。"""

    def __init__(self, embedding: EmbeddingService, vector_store: VectorStore) -> None:
        self.embedding = embedding
        self.vector_store = vector_store

    async def search(
        self,
        tenant_id: int,
        query: str,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """向量 cosine top-k + BM25-lite fallback，合并去重。"""
        t0 = time.time()

        # 1. 向量检索
        query_emb = await self.embedding.embed(query)
        vector_hits = self.vector_store.search(tenant_id, query_emb, top_k=top_k)

        # 2. BM25-lite fallback（从向量库取全部 chunks 做关键词匹配）
        all_chunks = self.vector_store._fetch_all(tenant_id)
        bm25_hits = self._bm25_search(query, all_chunks, top_k=top_k)

        # 3. 合并去重（按 content 去重，保留高分）
        seen_content: Dict[str, Dict[str, Any]] = {}
        for hit in vector_hits:
            key = hit["content"][:200]
            seen_content[key] = hit
        for hit in bm25_hits:
            key = hit["content"][:200]
            if key not in seen_content:
                seen_content[key] = hit

        merged = sorted(seen_content.values(), key=lambda x: -x["score"])[:top_k]
        took_ms = int((time.time() - t0) * 1000)

        return {"hits": merged, "took_ms": took_ms}

    def _bm25_search(
        self,
        query: str,
        all_chunks: list,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """BM25-lite 关键词检索。"""
        query_tokens = _tokenize(query)
        if not query_tokens or not all_chunks:
            return []

        # 计算平均文档长度
        doc_token_lists = []
        for row in all_chunks:
            doc_token_lists.append(_tokenize(row["content"]))
        avg_dl = sum(len(dt) for dt in doc_token_lists) / max(len(doc_token_lists), 1)

        scored = []
        for row, doc_tokens in zip(all_chunks, doc_token_lists):
            score = _bm25_score(query_tokens, doc_tokens, avg_dl)
            if score > 0:
                meta = {}
                try:
                    import json
                    meta = json.loads(row["metadata_json"] or "{}")
                except Exception:
                    pass
                scored.append({
                    "id": row["id"],
                    "doc_id": row["doc_id"],
                    "content": row["content"],
                    "metadata": meta,
                    "score": round(score, 4),
                })

        scored.sort(key=lambda x: -x["score"])
        return scored[:top_k]


__all__ = ["RetrievalService"]
