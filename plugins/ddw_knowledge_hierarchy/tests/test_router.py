"""ddw_knowledge_hierarchy router 端到端测试 — 2026-08-08 接入 services 后.

覆盖：
  1. health 端点（vector_store 状态）
  2. templates 端点（内置模板 8d/capa/quality_alert/coa/fmea）
  3. 知识桶创建/列表（真实DB）
  4. 文档上传→列表→检索→删除 全链路
  5. generate 文档生成（8d 模板）
  6. search 端点（无文档时优雅降级）
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

# 项目根入 sys.path（依赖 core.database / sdk）
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("DDW_JWT_SECRET", "test-secret-key-for-testing-32bytes-ok")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.ddw_knowledge_hierarchy import models as kh_models
from plugins.ddw_knowledge_hierarchy.router import router as kh_router


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """独立临时 SQLite 文件DB + 临时向量库（NullPool 避免事件循环绑定）。"""
    import asyncio
    import contextlib

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool


    db_file = tmp_path / "kh_test.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        poolclass=NullPool,
    )

    # 建 kh_* 表（独立 Base）— 短生命周期 loop，NullPool 每次新建连接无绑定问题
    async def _create_all():
        async with engine.begin() as conn:
            await conn.run_sync(kh_models.Base.metadata.create_all)

    asyncio.run(_create_all())

    maker = async_sessionmaker(engine, expire_on_commit=False)

    @contextlib.asynccontextmanager
    async def _fake_scope():
        async with maker() as s:
            try:
                yield s
            except Exception:
                await s.rollback()
                raise

    # 注意：router 顶部 `from core.database.session import session_scope` 是绑定拷贝，
    # 必须 patch router 模块自身的名字，而不是 core.database.session。
    import plugins.ddw_knowledge_hierarchy.router as router_module

    monkeypatch.setattr(router_module, "session_scope", _fake_scope)

    # 向量库注入临时路径
    vs_path = tmp_path / "kh_vector.db"
    from plugins.ddw_knowledge_hierarchy.router import set_vector_store_path

    set_vector_store_path(vs_path)

    app = FastAPI()
    app.include_router(kh_router)
    with TestClient(app) as c:
        yield c

    asyncio.run(engine.dispose())


# --------------------------------------------------------------------------- #
# health / templates
# --------------------------------------------------------------------------- #


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["plugin"] == "ddw-knowledge-hierarchy"
    assert data["status"] == "ok"
    assert data["vector_store"] == "ready"


def test_templates(client):
    resp = client.get("/templates")
    assert resp.status_code == 200
    names = [t["name"] for t in resp.json()]
    assert "8d" in names and "capa" in names and "coa" in names


# --------------------------------------------------------------------------- #
# buckets
# --------------------------------------------------------------------------- #


def test_bucket_create_and_list(client):
    resp = client.post("/buckets", json={"name": "质量体系", "description": "ISO文档"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "质量体系"

    resp = client.post("/buckets", json={"name": "质量体系"})
    assert resp.status_code == 409  # 重复名

    resp = client.get("/buckets")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# --------------------------------------------------------------------------- #
# 文档全链路：上传 → 列表 → 检索 → 删除
# --------------------------------------------------------------------------- #


def test_upload_list_search_delete(client):
    # 上传 markdown 文档
    md_content = (
        "# 设备操作规程\n\n"
        "## 启动步骤\n"
        "1. 打开电源\n"
        "2. 按下启动按钮\n"
        "3. 等待自检完成\n\n"
        "## 维护保养\n"
        "每周清洁过滤器，每月检查油位。"
    ).encode()
    resp = client.post(
        "/documents/upload",
        files={"file": ("设备操作规程.md", io.BytesIO(md_content), "text/markdown")},
        data={"knowledge_bucket": "default"},
    )
    assert resp.status_code == 201
    doc = resp.json()
    assert doc["id"] != "placeholder"  # 真实ID，非占位
    assert doc["title"] == "设备操作规程.md"

    # 列表
    resp = client.get("/documents")
    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) >= 1

    # 检索（flat 模式不依赖 LLM）
    resp = client.post(
        "/search/flat",
        json={"query": "启动按钮", "search_mode": "flat"},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["search_mode"] == "flat"
    assert len(result["retrieval_chunks"]) >= 1  # 真实检索到 chunk

    # 删除
    resp = client.delete(f"/documents/{doc['id']}")
    assert resp.status_code == 204

    # 删除后再查为空
    resp = client.get("/documents")
    assert resp.status_code == 200
    assert all(d["id"] != doc["id"] for d in resp.json())


# --------------------------------------------------------------------------- #
# generate 文档生成
# --------------------------------------------------------------------------- #


def test_generate_8d(client):
    resp = client.post(
        "/generate",
        json={
            "template_name": "8d",
            "variables": {"problem": "设备停机", "root_cause": "轴承磨损"},
            "title": "测试8D报告",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] != "placeholder"
    assert data["doc_type"] == "8d"
    assert len(data["content"]) > 0


# --------------------------------------------------------------------------- #
# search 优雅降级（空知识库）
# --------------------------------------------------------------------------- #


def test_search_empty_kb(client):
    resp = client.post(
        "/search/hierarchical",
        json={"query": "不存在的内容", "search_mode": "hybrid"},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["answer"] != "" or result["retrieval_chunks"] == []
