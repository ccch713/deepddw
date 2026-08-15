"""Embedding 抽象层 + 轻量实现。

设计：
- 抽象类 EmbeddingService 让上层不依赖具体实现
- SimpleEmbedding 基于词袋 + TF-IDF + L2 归一化（零依赖）
- 真实部署可替换为 sentence-transformers / bge-m3 / OpenAI Embedding
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from typing import Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


class EmbeddingService(ABC):
    """Embedding 服务抽象类。"""

    @abstractmethod
    async def embed(self, text: str) -> List[float]:
        ...

    @abstractmethod
    async def embed_batch(self, texts: Sequence[str]) -> List[List[float]]:
        ...

    @abstractmethod
    def dim(self) -> int:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    def cosine(self, a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)


# ─── SimpleEmbedding: hash trick + TF-IDF ───

_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fa5]+", re.IGNORECASE)


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    out: List[str] = []
    for m in _TOKEN_RE.finditer(text.lower()):
        tok = m.group(0)
        if not tok:
            continue
        if re.match(r"[\u4e00-\u9fa5]", tok):
            chars = list(tok)
            for i in range(len(chars) - 1):
                out.append(chars[i] + chars[i + 1])
            out.append(tok)
        else:
            out.append(tok)
    return out


class SimpleEmbedding(EmbeddingService):
    """基于 hash trick + TF-IDF 的简单 embedding（零依赖，开发/降级用）。"""

    def __init__(self, dim: int = 512) -> None:
        self._dim = dim
        self._doc_freq: Counter = Counter()
        self._doc_count: int = 0
        self._idf: Dict[str, float] = {}

    @property
    def name(self) -> str:
        return "simple-hash-tfidf"

    def dim(self) -> int:
        return self._dim

    async def embed(self, text: str) -> List[float]:
        return self._embed_sync(text, update_idf=False)

    async def embed_batch(self, texts: Sequence[str]) -> List[List[float]]:
        token_lists = [_tokenize(t) for t in texts]
        for toks in token_lists:
            if toks:
                self._doc_count += 1
                for tok in set(toks):
                    self._doc_freq[tok] += 1
        if self._doc_count:
            self._idf = {
                tok: math.log((1 + self._doc_count) / (1 + df)) + 1.0
                for tok, df in self._doc_freq.items()
            }
        return [self._embed_from_tokens(toks) for toks in token_lists]

    def fit_idf(self, all_texts: Sequence[str]) -> None:
        self._doc_count = 0
        self._doc_freq = Counter()
        for t in all_texts:
            toks = _tokenize(t)
            if toks:
                self._doc_count += 1
                for tok in set(toks):
                    self._doc_freq[tok] += 1
        if self._doc_count:
            self._idf = {
                tok: math.log((1 + self._doc_count) / (1 + df)) + 1.0
                for tok, df in self._doc_freq.items()
            }

    def _embed_sync(self, text: str, update_idf: bool = False) -> List[float]:
        toks = _tokenize(text)
        if update_idf:
            self._doc_count += 1
            for tok in set(toks):
                self._doc_freq[tok] += 1
        return self._embed_from_tokens(toks)

    def _embed_from_tokens(self, toks: List[str]) -> List[float]:
        if not toks:
            return [0.0] * self._dim
        tf: Counter = Counter(toks)
        total = sum(tf.values())
        vec = [0.0] * self._dim
        for tok, count in tf.items():
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            idx = h % self._dim
            sign = 1.0 if (h & 1) else -1.0
            idf = self._idf.get(tok, 1.0)
            vec[idx] += sign * (count / total) * idf
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec


_default_embedding: Optional[EmbeddingService] = None


def get_default_embedding() -> EmbeddingService:
    global _default_embedding
    if _default_embedding is None:
        _default_embedding = SimpleEmbedding(dim=512)
    return _default_embedding


def set_default_embedding(emb: EmbeddingService) -> None:
    global _default_embedding
    _default_embedding = emb
