"""测试 embedding fallback 和 chat 接口。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_project_root = str(Path(__file__).resolve().parents[3])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from plugins.ddw_ent_knowledge.core.embedding import (
    SimpleEmbedding,
    create_embedding_service,
)


class TestEmbeddingFallback:
    def test_simple_embedding_dim(self):
        """SimpleEmbedding 维度为 512。"""
        emb = SimpleEmbedding(dim=512)
        assert emb.dim() == 512
        assert emb.name == "simple-hash-tfidf"

    @pytest.mark.asyncio
    async def test_simple_embedding_embed(self):
        """SimpleEmbedding 能正常生成向量。"""
        emb = SimpleEmbedding(dim=512)
        vec = await emb.embed("测试文本")
        assert len(vec) == 512
        assert all(isinstance(v, float) for v in vec)
        # L2 归一化后范数应接近 1
        norm = sum(x * x for x in vec) ** 0.5
        assert abs(norm - 1.0) < 0.01 or norm == 0.0  # 空文本可能全零

    @pytest.mark.asyncio
    async def test_simple_embedding_batch(self):
        emb = SimpleEmbedding(dim=512)
        vecs = await emb.embed_batch(["文本一", "文本二", "文本三"])
        assert len(vecs) == 3
        assert all(len(v) == 512 for v in vecs)

    def test_create_embedding_no_key(self):
        """未配置 API Key 时应返回 SimpleEmbedding。"""
        # 确保环境变量中没有 key
        old_key = os.environ.pop("DDW_EMBEDDING_API_KEY", None)
        try:
            emb = create_embedding_service()
            assert isinstance(emb, SimpleEmbedding)
            assert emb.dim() == 512
        finally:
            if old_key:
                os.environ["DDW_EMBEDDING_API_KEY"] = old_key

    def test_create_embedding_with_key(self):
        """配置 API Key 时应返回 OpenAICompatEmbedding。"""
        from plugins.ddw_ent_knowledge.core.embedding import OpenAICompatEmbedding

        os.environ["DDW_EMBEDDING_API_KEY"] = "test-key"
        os.environ["DDW_EMBEDDING_BASE_URL"] = "http://localhost:8080"
        os.environ["DDW_EMBEDDING_MODEL"] = "test-model"
        os.environ["DDW_EMBEDDING_DIM"] = "768"
        try:
            emb = create_embedding_service()
            assert isinstance(emb, OpenAICompatEmbedding)
            assert emb.dim() == 768
        finally:
            for k in ["DDW_EMBEDDING_API_KEY", "DDW_EMBEDDING_BASE_URL", "DDW_EMBEDDING_MODEL", "DDW_EMBEDDING_DIM"]:
                os.environ.pop(k, None)
