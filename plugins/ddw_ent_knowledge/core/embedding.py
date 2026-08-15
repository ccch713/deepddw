"""Embedding 服务：抽象 + SimpleEmbedding + OpenAI 兼容客户端。"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
from abc import ABC, abstractmethod
from collections import Counter
from typing import Dict, List, Sequence

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


# ---------------------------------------------------------------------------
# SimpleEmbedding（零依赖兜底）
# ---------------------------------------------------------------------------

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
    """基于 hash trick + TF-IDF 的简单 embedding，维度固定 512。"""

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


# ---------------------------------------------------------------------------
# OpenAI 兼容 Embedding 客户端
# ---------------------------------------------------------------------------


class OpenAICompatEmbedding(EmbeddingService):
    """OpenAI 兼容 /v1/embeddings 接口。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "text-embedding-3-small",
        dim: int = 1536,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._dim = dim

    @property
    def name(self) -> str:
        return f"openai-compat-{self._model}"

    def dim(self) -> int:
        return self._dim

    async def embed(self, text: str) -> List[float]:
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: Sequence[str]) -> List[List[float]]:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base_url}/v1/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model, "input": list(texts)},
            )
            resp.raise_for_status()
            data = resp.json()
            items = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in items]


# ---------------------------------------------------------------------------
# 工厂：自动选择 embedding 实现
# ---------------------------------------------------------------------------


def create_embedding_service() -> EmbeddingService:
    """根据环境变量创建 embedding 服务。未配置 key 时降级 SimpleEmbedding。"""
    api_key = os.environ.get("DDW_EMBEDDING_API_KEY", "")
    if api_key:
        base_url = os.environ.get("DDW_EMBEDDING_BASE_URL", "https://api.openai.com")
        model = os.environ.get("DDW_EMBEDDING_MODEL", "text-embedding-3-small")
        dim = int(os.environ.get("DDW_EMBEDDING_DIM", "1536"))
        logger.info("Using OpenAI-compat embedding: %s (dim=%d)", model, dim)
        return OpenAICompatEmbedding(base_url=base_url, api_key=api_key, model=model, dim=dim)
    logger.info("No DDW_EMBEDDING_API_KEY, using SimpleEmbedding (dim=512)")
    return SimpleEmbedding(dim=512)


__all__ = [
    "EmbeddingService",
    "SimpleEmbedding",
    "OpenAICompatEmbedding",
    "create_embedding_service",
]
