"""Knowledge import from local files for ESG knowledge base."""

import os
from typing import Any

try:
    from .search import compute_tsvector
except ImportError:
    from search import compute_tsvector  # type: ignore[no-redef]


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 128) -> list[dict[str, Any]]:
    """Split text into overlapping chunks."""
    paragraphs = text.split("\n\n")
    chunks: list[dict[str, Any]] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) > chunk_size and current:
            chunks.append({
                "text": current.strip(),
                "token_count": len(current.split()),
                "tsvector": compute_tsvector(current.strip()),
            })
            # Keep overlap
            words = current.split()
            overlap_words = words[-overlap:] if len(words) > overlap else []
            current = " ".join(overlap_words) + "\n\n" + para
        else:
            current = current + "\n\n" + para if current else para
    if current.strip():
        chunks.append({
            "text": current.strip(),
            "token_count": len(current.split()),
            "tsvector": compute_tsvector(current.strip()),
        })
    return chunks


def import_markdown(file_path: str) -> dict[str, Any]:
    """Import a Markdown file as a knowledge document."""
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
    chunks = chunk_text(text)
    title = os.path.basename(file_path).replace(".md", "")
    return {
        "title": title,
        "text": text,
        "chunks": chunks,
        "chunk_count": len(chunks),
    }


def import_text(text: str, title: str = "Untitled") -> dict[str, Any]:
    """Import raw text as a knowledge document."""
    chunks = chunk_text(text)
    return {
        "title": title,
        "text": text,
        "chunks": chunks,
        "chunk_count": len(chunks),
    }
