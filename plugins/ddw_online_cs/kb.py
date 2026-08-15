"""DDW 在线客服插件 — 轻量知识库（纯 stdlib 混合检索）.

向量（md5 哈希桶）+ 关键词双路打分，无需外部依赖。
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_SUPPORTED_EXTS = {".md", ".yaml", ".yml", ".txt", ".json"}


class KnowledgeBase:
    """简单 RAG 知识库：分块 + 向量化 + 混合检索."""

    def __init__(self, knowledge_dir: str, chunk_size: int = 500, overlap: int = 50):
        self.knowledge_dir = Path(knowledge_dir)
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.chunks: List[Dict[str, Any]] = []
        self._load_all()

    # ---------------- 加载与分块 ----------------

    def _load_all(self) -> None:
        if not self.knowledge_dir.is_dir():
            logger.warning("Knowledge dir not found: %s", self.knowledge_dir)
            return
        for fp in sorted(self.knowledge_dir.rglob("*")):
            if not fp.is_file() or fp.suffix.lower() not in _SUPPORTED_EXTS:
                continue
            try:
                text = fp.read_text(encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                logger.warning("skip %s: %s", fp, exc)
                continue
            for para in self._chunk(text):
                self.chunks.append({
                    "content": para,
                    "source": str(fp.relative_to(self.knowledge_dir)),
                    "vector": self._embed(para),
                })
        logger.info("KB loaded %d chunks from %s", len(self.chunks), self.knowledge_dir)

    def _chunk(self, text: str) -> List[str]:
        # 按空行分段落，超长段落按句号切分，合并到 chunk_size 上限
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        out: List[str] = []
        buf = ""
        for p in paras:
            if len(buf) + len(p) <= self.chunk_size:
                buf = f"{buf}\n\n{p}" if buf else p
                continue
            if buf:
                out.append(buf)
            # 超长段落内部切分
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

    # ---------------- 向量化与检索 ----------------

    def _tokenize(self, text: str) -> List[str]:
        tokens: List[str] = []
        for char in text:
            if "\u4e00" <= char <= "\u9fff":
                tokens.append(char)
            elif char.isalnum():
                tokens.append(char.lower())
        return tokens

    def _embed(self, text: str, dim: int = 128) -> List[float]:
        vec = [0.0] * dim
        for tok in self._tokenize(text)[:4000]:
            idx = int(hashlib.md5(tok.encode()).hexdigest(), 16) % dim
            vec[idx] += 1.0
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    def _cosine(self, a: List[float], b: List[float]) -> float:
        return sum(x * y for x, y in zip(a, b))

    def _keyword_score(self, query: str, text: str) -> float:
        q_toks = set(self._tokenize(query))
        if not q_toks:
            return 0.0
        t_toks = set(self._tokenize(text))
        return len(q_toks & t_toks) / len(q_toks)

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if not self.chunks:
            return []
        qv = self._embed(query)
        scored = []
        for c in self.chunks:
            vec_score = self._cosine(qv, c["vector"])
            kw_score = self._keyword_score(query, c["content"])
            total = vec_score * 0.7 + kw_score * 0.3
            if total > 0.01:
                scored.append((total, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"content": c["content"], "source": c["source"], "score": round(s, 4)}
            for s, c in scored[:top_k]
        ]
