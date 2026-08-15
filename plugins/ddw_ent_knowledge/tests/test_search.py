"""测试检索。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_project_root = str(Path(__file__).resolve().parents[3])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from plugins.ddw_ent_knowledge.core.embedding import SimpleEmbedding
from plugins.ddw_ent_knowledge.core.vector_store import VectorStore
from plugins.ddw_ent_knowledge.services.retrieval_service import RetrievalService


def _ingest_doc(vs: VectorStore, emb: SimpleEmbedding, tenant_id: int, doc_id: str, chunks: list):
    """辅助：入库一批 chunks。"""
    emb.fit_idf(chunks)
    embeddings = [asyncio.run(emb.embed(c)) for c in chunks]
    vs.add(tenant_id=tenant_id, doc_id=doc_id, contents=chunks, embeddings=embeddings)


class TestVectorSearch:
    def test_search_relevant_doc(self, vector_store, simple_embedding):
        """语义相近 query 应命中正确文档 top1。"""
        doc1_chunks = ["人工智能是计算机科学的一个分支，致力于创建智能系统。"]
        doc2_chunks = ["今天天气很好，适合出门散步。"]
        doc3_chunks = ["机器学习是人工智能的核心技术之一。"]

        _ingest_doc(vector_store, simple_embedding, 1, "doc_ai", doc1_chunks)
        _ingest_doc(vector_store, simple_embedding, 1, "doc_weather", doc2_chunks)
        _ingest_doc(vector_store, simple_embedding, 1, "doc_ml", doc3_chunks)

        # 搜索 AI 相关
        query_emb = asyncio.run(simple_embedding.embed("什么是人工智能"))
        hits = vector_store.search(1, query_emb, top_k=3)
        assert len(hits) >= 1
        # top1 应该是 AI 相关文档
        top1_content = hits[0]["content"]
        assert "人工智能" in top1_content or "机器学习" in top1_content

    def test_search_no_match(self, vector_store, simple_embedding):
        """无文档时返回空列表。"""
        query_emb = asyncio.run(simple_embedding.embed("测试"))
        hits = vector_store.search(999, query_emb, top_k=5)
        assert hits == []


class TestRetrievalService:
    @pytest.mark.asyncio
    async def test_search_with_fallback(self, vector_store, simple_embedding):
        """BM25 fallback 在向量匹配弱时也能返回结果。"""
        doc_chunks = ["DDW 平台支持多种插件扩展，包括知识库、客服、培训等模块。"]
        simple_embedding.fit_idf(doc_chunks)
        embeddings = await simple_embedding.embed_batch(doc_chunks)
        vector_store.add(tenant_id=1, doc_id="doc_ddw", contents=doc_chunks, embeddings=embeddings)

        retrieval = RetrievalService(simple_embedding, vector_store)
        result = await retrieval.search(1, "DDW 插件扩展", top_k=5)

        assert "hits" in result
        assert "took_ms" in result
        assert isinstance(result["took_ms"], int)
        assert len(result["hits"]) >= 1
