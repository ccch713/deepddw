"""Full-text search + semantic search + hybrid search for ESG knowledge."""

from __future__ import annotations

import math
import re
from typing import Any


def compute_tsvector(text: str) -> str:
    """Simple Chinese + English tokenization for full-text search."""
    tokens = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+", text.lower())
    return " ".join(tokens)


def keyword_search(
    query: str,
    chunks: list[dict[str, Any]],
    top_k: int = 10,
    customer_id: str | None = None,
    framework: str | None = None,
) -> list[dict[str, Any]]:
    """Simple keyword-based search using token overlap."""
    query_tokens = set(re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+", query.lower()))
    results: list[dict[str, Any]] = []
    for chunk in chunks:
        # Filter by customer_id if provided
        if customer_id and chunk.get("customer_id") != customer_id:
            continue
        chunk_tokens = set(chunk.get("tsvector", "").split())
        overlap = query_tokens & chunk_tokens
        if overlap:
            score = len(overlap) / len(query_tokens) if query_tokens else 0
            results.append({**chunk, "score": score, "match_type": "keyword"})
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def semantic_search(
    query_embedding: list[float],
    chunks: list[dict[str, Any]],
    top_k: int = 10,
    customer_id: str | None = None,
    framework: str | None = None,
) -> list[dict[str, Any]]:
    """Search by embedding similarity."""
    results: list[dict[str, Any]] = []
    for chunk in chunks:
        if customer_id and chunk.get("customer_id") != customer_id:
            continue
        emb = chunk.get("embedding")
        if emb:
            score = cosine_similarity(query_embedding, emb)
            results.append({**chunk, "score": score, "match_type": "semantic"})
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def hybrid_search(
    query: str,
    query_embedding: list[float] | None,
    chunks: list[dict[str, Any]],
    keyword_weight: float = 0.3,
    semantic_weight: float = 0.7,
    top_k: int = 10,
    customer_id: str | None = None,
    framework: str | None = None,
) -> list[dict[str, Any]]:
    """Combine keyword and semantic search."""
    keyword_results = keyword_search(
        query, chunks, top_k=top_k * 2, customer_id=customer_id, framework=framework
    )

    semantic_results: list[dict[str, Any]] = []
    if query_embedding:
        semantic_results = semantic_search(
            query_embedding, chunks, top_k=top_k * 2, customer_id=customer_id, framework=framework
        )

    # Merge by chunk id
    scores: dict[str, dict[str, Any]] = {}
    for r in keyword_results:
        chunk_id = r["id"]
        if chunk_id not in scores:
            scores[chunk_id] = {"chunk": r}
        scores[chunk_id]["keyword"] = r["score"]

    for r in semantic_results:
        chunk_id = r["id"]
        if chunk_id not in scores:
            scores[chunk_id] = {"chunk": r}
        scores[chunk_id]["semantic"] = r["score"]

    # Combine scores
    combined: list[dict[str, Any]] = []
    for _chunk_id, s in scores.items():
        kw = s.get("keyword", 0) * keyword_weight
        sem = s.get("semantic", 0) * semantic_weight
        combined.append({**s["chunk"], "score": kw + sem, "match_type": "hybrid"})
    combined.sort(key=lambda x: x["score"], reverse=True)
    return combined[:top_k]
