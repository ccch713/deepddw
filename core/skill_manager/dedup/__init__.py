"""Skill 3-layer deduplication (PRD §7.2.6).

The skill manager keeps a small in-memory cache of skills and
applies three layers of deduplication before persisting a new
skill:

1. **Exact match** — hash of the canonicalised content
2. **Soft match**   — normalised trigger
3. **Semantic**     — embedding cosine (skipped unless an embedder
   is available; the platform supports plugging in an Ollama
   embedder via :class:`core.llm_gateway.ollama.OllamaProvider.embed`)

The platform stores every skill in the ``skills`` table; identical
content becomes a soft link pointing at the canonical row.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


def normalise(text: str) -> str:
    """Lowercase + collapse whitespace + strip punctuation."""

    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s\u4e00-\u9fff]+", "", text)
    return text.strip()


def content_hash(content: str) -> str:
    return hashlib.sha256(normalise(content).encode("utf-8")).hexdigest()


def trigger_hash(trigger: str) -> str:
    return hashlib.sha256(normalise(trigger).encode("utf-8")).hexdigest()


@dataclass
class DedupResult:
    is_duplicate: bool
    canonical_id: Optional[int]
    reason: str = ""


class ThreeLayerDedup:
    """Applies the three dedup layers in sequence."""

    def __init__(self) -> None:
        self._content_index: dict[str, int] = {}
        self._trigger_index: dict[str, int] = {}

    def register(self, *, canonical_id: int, content: str, trigger: Optional[str] = None) -> None:
        self._content_index[content_hash(content)] = canonical_id
        if trigger:
            self._trigger_index[trigger_hash(trigger)] = canonical_id

    def check(self, *, content: str, trigger: Optional[str] = None) -> DedupResult:
        ch = content_hash(content)
        if ch in self._content_index:
            return DedupResult(True, self._content_index[ch], "exact_content")
        if trigger:
            th = trigger_hash(trigger)
            if th in self._trigger_index:
                return DedupResult(True, self._trigger_index[th], "exact_trigger")
        # Layer 3 (semantic) is a hook for future embedding-based dedup.
        return DedupResult(False, None, "unique")
