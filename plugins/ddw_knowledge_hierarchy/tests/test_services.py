"""Tests for Knowledge Hierarchy plugin services."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

# ─── Chunker Tests ───

class TestChunker:
    def test_empty_text(self):
        from plugins.ddw_knowledge_hierarchy.services.chunker import chunk_text
        chunks = chunk_text("")
        assert chunks == []

    def test_short_text_single_chunk(self):
        from plugins.ddw_knowledge_hierarchy.services.chunker import chunk_text
        chunks = chunk_text("这是一段短文本。")
        assert len(chunks) == 1
        assert "短文本" in chunks[0].content

    def test_long_text_multiple_chunks(self):
        from plugins.ddw_knowledge_hierarchy.services.chunker import chunk_text
        # 生成足够长的文本
        text = "这是一段测试文本，用于验证分块功能。" * 100
        chunks = chunk_text(text, chunk_size=200)
        assert len(chunks) > 1
        # 每个 chunk 的 token 数不超过限制（粗略检查）
        for c in chunks:
            assert c.token_count <= 400  # 允许一些溢出

    def test_markdown_headings(self):
        from plugins.ddw_knowledge_hierarchy.services.chunker import chunk_text
        text = "# 第一章\n\n这是第一章的内容。\n\n## 1.1 节\n\n这是1.1节的内容。"
        chunks = chunk_text(text, section_title="第一章")
        assert len(chunks) >= 1


# ─── Embedding Tests ───

class TestEmbedding:
    def test_simple_embedding_dimension(self):
        from plugins.ddw_knowledge_hierarchy.services.embedding_service import (
            SimpleEmbedding,
        )
        emb = SimpleEmbedding(dim=128)
        assert emb.dim() == 128

    @pytest.mark.asyncio
    async def test_embed_returns_vector(self):
        from plugins.ddw_knowledge_hierarchy.services.embedding_service import (
            SimpleEmbedding,
        )
        emb = SimpleEmbedding(dim=256)
        vec = await emb.embed("测试文本")
        assert len(vec) == 256
        # L2 归一化后模长应该接近 1
        norm = math.sqrt(sum(x * x for x in vec))
        assert abs(norm - 1.0) < 0.01 or norm == 0.0

    @pytest.mark.asyncio
    async def test_embed_batch(self):
        from plugins.ddw_knowledge_hierarchy.services.embedding_service import (
            SimpleEmbedding,
        )
        emb = SimpleEmbedding(dim=128)
        vecs = await emb.embed_batch(["文本1", "文本2", "文本3"])
        assert len(vecs) == 3
        assert all(len(v) == 128 for v in vecs)

    def test_cosine_similarity(self):
        from plugins.ddw_knowledge_hierarchy.services.embedding_service import (
            SimpleEmbedding,
        )
        emb = SimpleEmbedding(dim=4)
        a = [1.0, 0.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0, 0.0]
        assert abs(emb.cosine(a, b) - 1.0) < 0.001
        c = [0.0, 1.0, 0.0, 0.0]
        assert abs(emb.cosine(a, c)) < 0.001


# ─── VectorStore Tests ───

class TestVectorStore:
    def test_add_and_search(self, tmp_path):
        from plugins.ddw_knowledge_hierarchy.services.vector_store import VectorStore
        store = VectorStore(tmp_path / "test.db")

        # 添加向量
        store.add(
            tenant_id=1,
            doc_id="doc1",
            chunk_ids=["c1", "c2"],
            contents=["这是关于食品安全的内容", "这是关于质量控制的内容"],
            embeddings=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        )

        # 搜索
        results = store.search(
            tenant_id=1,
            query_embedding=[1.0, 0.0, 0.0],
            top_k=5,
        )
        assert len(results) == 2
        assert results[0]["score"] > results[1]["score"]  # 第一个更相似

    def test_delete_by_doc(self, tmp_path):
        from plugins.ddw_knowledge_hierarchy.services.vector_store import VectorStore
        store = VectorStore(tmp_path / "test.db")
        store.add(1, "doc1", ["c1"], ["text"], [[1.0, 0.0]])
        assert store.count(1) == 1
        store.delete_by_doc(1, "doc1")
        assert store.count(1) == 0

    def test_multi_tenant_isolation(self, tmp_path):
        from plugins.ddw_knowledge_hierarchy.services.vector_store import VectorStore
        store = VectorStore(tmp_path / "test.db")
        store.add(1, "doc1", ["c1"], ["tenant1 text"], [[1.0, 0.0]])
        store.add(2, "doc2", ["c2"], ["tenant2 text"], [[0.0, 1.0]])
        results = store.search(1, [1.0, 0.0], top_k=10)
        assert len(results) == 1
        assert results[0]["doc_id"] == "doc1"


# ─── Document Parser Tests ───

class TestDocumentParser:
    def test_parse_markdown(self, tmp_path):
        from plugins.ddw_knowledge_hierarchy.services.document_parser import (
            parse_document,
        )
        md_file = tmp_path / "test.md"
        md_file.write_text("# 测试文档\n\n这是测试内容。\n\n## 第一节\n\n第一节内容。")
        result = parse_document(md_file)
        assert result.title == "test"
        assert result.file_type == "md"
        assert len(result.raw_text) > 0
        assert len(result.sections) >= 1

    def test_parse_text(self, tmp_path):
        from plugins.ddw_knowledge_hierarchy.services.document_parser import (
            parse_document,
        )
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("纯文本内容\n第二行")
        result = parse_document(txt_file)
        assert result.file_type == "txt"
        assert "纯文本" in result.raw_text

    def test_parse_json(self, tmp_path):
        from plugins.ddw_knowledge_hierarchy.services.document_parser import (
            parse_document,
        )
        json_file = tmp_path / "test.json"
        json_file.write_text(json.dumps({"key": "value"}, ensure_ascii=False))
        result = parse_document(json_file)
        assert result.file_type == "json"
        assert "key" in result.raw_text

    def test_file_not_found(self):
        from plugins.ddw_knowledge_hierarchy.services.document_parser import (
            parse_document,
        )
        with pytest.raises(FileNotFoundError):
            parse_document(Path("/nonexistent/file.pdf"))


# ─── Doc Generator Tests ───

class TestDocGenerator:
    def test_builtin_templates_exist(self):
        from plugins.ddw_knowledge_hierarchy.services.doc_generator import (
            BUILTIN_TEMPLATES,
        )
        assert "8d" in BUILTIN_TEMPLATES
        assert "capa" in BUILTIN_TEMPLATES
        assert "quality_alert" in BUILTIN_TEMPLATES
        assert "coa" in BUILTIN_TEMPLATES
        assert "fmea" in BUILTIN_TEMPLATES

    def test_template_has_required_fields(self):
        from plugins.ddw_knowledge_hierarchy.services.doc_generator import (
            BUILTIN_TEMPLATES,
        )
        for name, tpl in BUILTIN_TEMPLATES.items():
            assert "name" in tpl
            assert "template_type" in tpl
            assert "content_template" in tpl
            assert "industry" in tpl


# ─── Model Tests ───

class TestModels:
    def test_model_imports(self):
        from plugins.ddw_knowledge_hierarchy.models import (
            Document,
            DocumentChunk,
            DocumentTemplate,
            TreeNode,
        )
        assert Document.__tablename__ == "kh_documents"
        assert TreeNode.__tablename__ == "kh_tree_nodes"
        assert DocumentChunk.__tablename__ == "kh_chunks"
        assert DocumentTemplate.__tablename__ == "kh_templates"


# ─── Router Tests ───

class TestRouter:
    def test_health_endpoint(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from plugins.ddw_knowledge_hierarchy.router import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["plugin"] == "ddw-knowledge-hierarchy"

    def test_list_templates_endpoint(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from plugins.ddw_knowledge_hierarchy.router import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.get("/templates")
        assert resp.status_code == 200
        templates = resp.json()
        assert len(templates) >= 5
        types = {t["template_type"] for t in templates}
        assert "8d" in types
        assert "capa" in types
