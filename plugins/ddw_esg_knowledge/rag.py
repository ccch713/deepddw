"""RAG retrieval interface for ESG knowledge base."""

from __future__ import annotations

from typing import Any

try:
    from .search import keyword_search
except ImportError:
    from search import keyword_search  # type: ignore[no-redef]


def retrieve_context(
    question: str,
    chunks: list[dict[str, Any]],
    top_k: int = 5,
    max_tokens: int = 4000,
    customer_id: str | None = None,
) -> dict[str, Any]:
    """RAG retrieval: search + build context for LLM."""
    results = keyword_search(question, chunks, top_k=top_k, customer_id=customer_id)
    context_parts: list[dict[str, Any]] = []
    total_tokens = 0
    for r in results:
        token_count = r.get("token_count", 0) or 0
        if total_tokens + token_count > max_tokens:
            break
        context_parts.append({
            "source": r.get("doc_title", "Unknown"),
            "text": r["text"],
            "relevance": r["score"],
        })
        total_tokens += token_count
    return {
        "context": context_parts,
        "total_tokens": total_tokens,
    }


def build_rag_context(
    question: str,
    chunks: list[dict[str, Any]],
    top_k: int = 5,
    max_tokens: int = 4000,
    customer_id: str | None = None,
) -> dict[str, Any]:
    """Build a complete RAG context with source attribution."""
    result = retrieve_context(
        question, chunks, top_k=top_k, max_tokens=max_tokens, customer_id=customer_id
    )
    # Build formatted context string
    context_str_parts: list[str] = []
    for i, item in enumerate(result["context"], 1):
        context_str_parts.append(
            f"[Source {i}: {item['source']} (relevance: {item['relevance']:.2f})]\n{item['text']}"
        )
    result["context_str"] = "\n\n".join(context_str_parts)
    return result
