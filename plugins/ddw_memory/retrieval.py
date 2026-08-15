"""ddw_memory 四层穿透检索 — 关键词 + 向量 + 层级穿透。"""
from __future__ import annotations

import logging
import math

from .models import MemoryLayer

logger = logging.getLogger(__name__)

# 层级权重
LAYER_WEIGHTS: dict[str, float] = {
    MemoryLayer.PERSONAL.value: 1.2,
    MemoryLayer.POSITION.value: 1.1,
    MemoryLayer.DEPARTMENT.value: 1.0,
    MemoryLayer.ENTERPRISE.value: 0.9,
}


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算两个向量的余弦相似度。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _keyword_score(query: str, content: str) -> float:
    """关键词匹配分数（支持中文 ngram）。"""
    if not content:
        return 0.0
    query_lower = query.lower()
    content_lower = content.lower()
    # 完整匹配
    if query_lower in content_lower:
        return 1.0
    # 多词空格分词匹配
    words = [w.strip() for w in query_lower.split() if w.strip() and len(w.strip()) >= 2]
    if len(words) >= 2:
        matched = sum(1 for w in words if w in content_lower)
        return matched / max(len(words), 1)
    # 中文无空格 / 单一长词 → 2-gram 匹配
    if len(query_lower) >= 4:
        ngrams = [query_lower[i:i+2] for i in range(len(query_lower) - 1)]
        matched = sum(1 for g in ngrams if g in content_lower)
        return matched / max(len(ngrams), 1)
    # 短查询：任何字符匹配
    if len(query_lower) >= 2:
        return 1.0 if any(c in content_lower for c in query_lower) else 0.0
    return 0.0


def _rrf_merge(keyword_hits: list[dict], vector_hits: list[dict], k: int = 60) -> list[dict]:
    """Reciprocal Rank Fusion 合并两个排序列表。"""
    scores: dict[str, float] = {}
    entry_map: dict[str, dict] = {}

    for rank, hit in enumerate(keyword_hits):
        uid = hit["uuid"]
        scores[uid] = scores.get(uid, 0.0) + 1.0 / (k + rank + 1)
        entry_map[uid] = hit

    for rank, hit in enumerate(vector_hits):
        uid = hit["uuid"]
        scores[uid] = scores.get(uid, 0.0) + 1.0 / (k + rank + 1)
        entry_map[uid] = hit

    merged = []
    for uid, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        hit = entry_map[uid].copy()
        hit["score"] = score
        merged.append(hit)

    return merged


__all__ = ["LAYER_WEIGHTS", "_cosine_similarity", "_keyword_score", "_rrf_merge"]
