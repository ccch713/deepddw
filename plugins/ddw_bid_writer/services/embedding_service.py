"""Embedding 抽象层 + 轻量实现。

设计：
- 抽象类 ``EmbeddingService`` 让上层不依赖具体实现
- ``SimpleEmbedding`` 基于词袋 + TF-IDF + L2 归一化（零依赖，但效果一般）
- 真实部署可替换为 sentence-transformers / bge / OpenAI Embedding

注意：simple 实现的相似度质量有限，但对"主题分组"够用。
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from typing import Dict, List, Sequence

logger = logging.getLogger(__name__)


class EmbeddingService(ABC):
    """Embedding 服务抽象类。"""

    @abstractmethod
    async def embed(self, text: str) -> List[float]:
        """把单段文本编码为向量。"""
        ...

    @abstractmethod
    async def embed_batch(self, texts: Sequence[str]) -> List[List[float]]:
        """批量编码。"""
        ...

    @abstractmethod
    def dim(self) -> int:
        """向量维度。"""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    def cosine(self, a: List[float], b: List[float]) -> float:
        """计算余弦相似度（同步，纯数学）。"""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)


# ---------------------------------------------------------------------------
# SimpleEmbedding：基于词袋 + hash trick + 长度归一化
# ---------------------------------------------------------------------------


_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fa5]+", re.IGNORECASE)


def _tokenize(text: str) -> List[str]:
    """中英文粗粒度分词：英文按词、中文按整段（保留语义块）。"""
    if not text:
        return []
    out: List[str] = []
    for m in _TOKEN_RE.finditer(text.lower()):
        tok = m.group(0)
        if not tok:
            continue
        if re.match(r"[\u4e00-\u9fa5]", tok):
            # 中文按 2 字 bigram
            chars = list(tok)
            for i in range(len(chars) - 1):
                out.append(chars[i] + chars[i + 1])
            out.append(tok)  # 保留整体
        else:
            out.append(tok)
    return out


class SimpleEmbedding(EmbeddingService):
    """基于 hash trick + TF-IDF 的简单 embedding。

    - 维度固定（默认 512）
    - 完全离线、零依赖
    - 适合开发/降级场景，真实部署替换为 bge-large-zh
    """

    def __init__(self, dim: int = 512) -> None:
        self._dim = dim
        # IDF 统计：词 → 文档数
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
        # 一次性更新 IDF
        token_lists = [_tokenize(t) for t in texts]
        for toks in token_lists:
            if toks:
                self._doc_count += 1
                for tok in set(toks):
                    self._doc_freq[tok] += 1
        # 重算 IDF
        if self._doc_count:
            self._idf = {
                tok: math.log((1 + self._doc_count) / (1 + df)) + 1.0
                for tok, df in self._doc_freq.items()
            }
        return [self._embed_from_tokens(toks) for toks in token_lists]

    def fit_idf(self, all_texts: Sequence[str]) -> None:
        """外部触发 IDF 重算（用于：bootstrap 时一次性喂全部语料）。"""
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
        # TF
        tf: Counter = Counter(toks)
        total = sum(tf.values())
        # 映射到 dim 维（hash trick）
        vec = [0.0] * self._dim
        for tok, count in tf.items():
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            idx = h % self._dim
            # 用 h 的最低位做符号（确保有正有负）
            sign = 1.0 if (h & 1) else -1.0
            idf = self._idf.get(tok, 1.0)
            vec[idx] += sign * (count / total) * idf
        # L2 归一化
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec


# ---------------------------------------------------------------------------
# 服务单例（lazy）
# ---------------------------------------------------------------------------


_default_embedding: EmbeddingService | None = None


def get_default_embedding() -> EmbeddingService:
    """获取默认 embedding 服务（进程级单例）。"""
    global _default_embedding
    if _default_embedding is None:
        _default_embedding = SimpleEmbedding(dim=512)
    return _default_embedding


def set_default_embedding(emb: EmbeddingService) -> None:
    """测试/部署时注入自定义 embedding。"""
    global _default_embedding
    _default_embedding = emb


__all__ = [
    "EmbeddingService",
    "SimpleEmbedding",
    "get_default_embedding",
    "set_default_embedding",
]
