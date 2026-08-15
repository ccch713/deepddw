"""测试文档入库。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


_project_root = str(Path(__file__).resolve().parents[3])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from plugins.ddw_ent_knowledge.core.chunker import chunk_text


class TestChunker:
    def test_chunk_text_basic(self):
        text = "## 标题一\n\n" + "内容" * 200 + "\n\n## 标题二\n\n" + "更多" * 200
        chunks = chunk_text(text)
        assert len(chunks) >= 2
        assert all(len(c) >= 20 for c in chunks)

    def test_chunk_text_empty(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_chunk_text_short(self):
        text = "这是一段很短的文本。"
        chunks = chunk_text(text)
        # 短文本可能不分块
        assert isinstance(chunks, list)


class TestIngestFlow:
    """测试完整入库流程（同步方式）。"""

    def test_embed_and_store(self, vector_store, simple_embedding):
        """分块 → embedding → 写入向量库 → 检索。"""
        text = "## 产品介绍\n\nDDW 是一个企业级 AI 平台。\n\n## 技术架构\n\n基于微服务架构设计。"
        chunks = chunk_text(text)
        assert len(chunks) >= 1

        # 同步 embedding
        simple_embedding.fit_idf(chunks)
        embeddings = []
        for c in chunks:
            embeddings.append(asyncio.run(simple_embedding.embed(c)))

        # 写入
        ids = vector_store.add(tenant_id=1, doc_id="doc_001", contents=chunks, embeddings=embeddings)
        assert len(ids) == len(chunks)
        assert all(isinstance(i, int) for i in ids)

        # 计数
        assert vector_store.count(1) == len(chunks)

    def test_delete_by_doc(self, vector_store, simple_embedding):
        chunks = ["chunk a", "chunk b"]
        simple_embedding.fit_idf(chunks)
        embeddings = [asyncio.run(simple_embedding.embed(c)) for c in chunks]
        vector_store.add(tenant_id=1, doc_id="doc_del", contents=chunks, embeddings=embeddings)

        deleted = vector_store.delete_by_doc(1, "doc_del")
        assert deleted == 2
        assert vector_store.count(1) == 0
