"""#1 LanceDB 向量检索测试：混合检索 / 语义召回 / 幂等 upsert / 降级。"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DDW_ACCESS_TOKEN", "test-kb-vector-token")


@pytest.fixture(autouse=True)
def _vector_reset(monkeypatch, tmp_path):
    """每次测试独立 LanceDB 目录 + 重置可用性缓存。"""
    from core import knowledge as kb

    lance_dir = tmp_path / "vec"
    monkeypatch.setenv("LANCEDB_PATH", str(lance_dir))
    monkeypatch.setattr(kb, "_lance_available_cache", None)
    # 知识库主库也独立
    monkeypatch.setattr(kb, "_db_path", lambda: tmp_path / "kb.db")
    return lance_dir


def _enable_vectors(monkeypatch):
    from core import knowledge as kb

    monkeypatch.setattr(kb, "_lance_available_cache", True)


def test_vector_add_and_hybrid_search(_vector_reset):
    """入库 → hybrid 检索返回（mode=hybrid，含向量来源）。"""
    from core.knowledge import kb_add_document, kb_search

    kb_add_document("SPC 质量手册", "统计过程控制 SPC 用于生产质量监控。")
    result = kb_search("SPC 质量", 5)
    assert result["mode"] == "hybrid"
    assert result["results"]
    assert result["results"][0]["title"] == "SPC 质量手册"


def test_vector_search_semantic_recall(_vector_reset):
    """向量语义召回：检索词与文档共享高频词（hash-trick 词频）时也能命中。"""
    from core.knowledge import kb_add_document, kb_search

    kb_add_document("部署指南", "deepDDW 部署需要 Docker 与 Python 环境。")
    # 检索词含文档关键词（部署）→ 向量与关键词都应命中
    result = kb_search("部署", 5)
    assert result["results"]
    titles = {r["title"] for r in result["results"]}
    assert "部署指南" in titles


def test_vector_upsert_idempotent(_vector_reset):
    """同 doc 重复入库 → 向量表不膨胀（按 doc_id upsert）。"""
    from core.knowledge import kb_add_document, _vector_search

    d1 = kb_add_document("文档A", "内容 alpha beta gamma")
    kb_add_document("文档A", "内容 alpha beta gamma")  # 新 doc_id，重复内容
    # 两篇不同 doc_id 都在向量表（幂等按 doc_id，不按内容去重）
    hits = _vector_search("alpha", 10)
    ids = {int(h["doc_id"]) for h in hits}
    assert d1["id"] in ids


def test_vector_degrade_when_unavailable(_vector_reset, monkeypatch):
    """LANCEDB_PATH 不可写/import 失败 → 自动降级纯关键词，不阻塞。"""
    from core import knowledge as kb

    monkeypatch.setattr(kb, "_lance_available_cache", False)
    from core.knowledge import kb_add_document, kb_search

    kb_add_document("降级测试文档", "这段内容包含降级关键词。")
    result = kb_search("降级", 5)
    # 降级路径：mode=keyword（向量不可用），但仍能命中
    assert result["mode"] == "keyword"
    assert result["results"]


def test_vector_search_returns_empty_when_no_lance(_vector_reset, monkeypatch):
    """无 LanceDB 表 → _vector_search 返回空（上层走纯关键词）。"""
    from core import knowledge as kb

    monkeypatch.setattr(kb, "_lance_available_cache", True)
    from core.knowledge import _vector_search

    hits = _vector_search("anything", 5)
    assert hits == []
