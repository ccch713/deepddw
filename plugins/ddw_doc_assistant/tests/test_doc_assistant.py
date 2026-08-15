"""ddw_doc_assistant 端到端测试。

覆盖：
  1. health 端点
  2. 文档上传（Markdown）
  3. 文档列表
  4. 文档删除
  5. RAG 问答（有文档时）
  6. RAG 问答（空知识库）
  7. 文档 chunks 查询
  8. 按部门筛选
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

# 项目根入 sys.path
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("DDW_JWT_SECRET", "test-secret-key-for-testing-32bytes-ok")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """独立临时 SQLite + 临时向量库。"""
    import asyncio
    import contextlib

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    db_file = tmp_path / "da_test.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        poolclass=NullPool,
    )

    # 建表
    from plugins.ddw_doc_assistant import models as da_models

    async def _create_all():
        async with engine.begin() as conn:
            await conn.run_sync(da_models.Base.metadata.create_all)

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

    # Patch session_scope
    import plugins.ddw_doc_assistant.router as router_module

    monkeypatch.setattr(router_module, "session_scope", _fake_scope)

    # 向量库临时路径
    vs_path = tmp_path / "da_vector.db"
    from plugins.ddw_doc_assistant.router import set_vector_store_path

    set_vector_store_path(vs_path)

    app = FastAPI()
    from plugins.ddw_doc_assistant.router import router as da_router

    app.include_router(da_router)
    with TestClient(app) as c:
        yield c

    asyncio.run(engine.dispose())


# ─── 辅助 ───

def _upload_md(client, name: str = "测试文档.md", content: str = ""):
    """上传一个 Markdown 文件。"""
    if not content:
        content = (
            "# 设计院技术规范\n\n"
            "## 1. 总则\n"
            "本规范适用于设计院各类工程项目。\n\n"
            "## 2. 结构设计\n"
            "结构设计应满足安全性和耐久性要求。\n\n"
            "## 3. 设备选型\n"
            "设备选型应考虑能效比和维护成本。"
        )
    return client.post(
        "/documents/upload",
        files={"file": (name, io.BytesIO(content.encode("utf-8")), "text/markdown")},
        data={"uploader": "张工", "department": "结构所"},
    )


# ─── 测试 ───


def test_health(client):
    """健康检查端点正常。"""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["plugin"] == "ddw-doc-assistant"
    assert data["status"] == "ok"
    assert data["vector_store"] == "ready"


def test_upload_document(client):
    """上传 Markdown 文档，解析并入库。"""
    resp = _upload_md(client)
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] != ""
    assert data["title"] == "测试文档.md"
    assert data["file_type"] == "md"
    assert data["chunk_count"] >= 1
    assert data["vector_indexed"] is True


def test_list_documents(client):
    """上传后能列出来。"""
    _upload_md(client, "doc1.md")
    _upload_md(client, "doc2.md", "# 另一个文档\n\n内容不同。")
    resp = client.get("/documents")
    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) >= 2
    titles = {d["title"] for d in docs}
    assert "doc1.md" in titles
    assert "doc2.md" in titles


def test_delete_document(client):
    """删除文档后不再出现在列表中。"""
    resp = _upload_md(client)
    doc_id = resp.json()["id"]

    resp = client.delete(f"/documents/{doc_id}")
    assert resp.status_code == 204

    resp = client.get("/documents")
    assert all(d["id"] != doc_id for d in resp.json())


def test_delete_nonexistent(client):
    """删除不存在的文档返回 404。"""
    resp = client.delete("/documents/nonexistent-id")
    assert resp.status_code == 404


def test_query_with_docs(client):
    """上传文档后进行 RAG 问答，返回答案和来源。"""
    _upload_md(client)
    resp = client.post(
        "/documents/query",
        json={"question": "结构设计有什么要求？", "top_k": 3},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert len(data["answer"]) > 0
    assert isinstance(data["sources"], list)
    assert len(data["sources"]) >= 1
    # 来源包含必要字段
    src = data["sources"][0]
    assert "chunk_id" in src
    assert "doc_id" in src
    assert "content" in src
    assert "score" in src


def test_query_empty_kb(client):
    """空知识库问答不报错。"""
    resp = client.post(
        "/documents/query",
        json={"question": "不存在的内容", "top_k": 5},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert data["sources"] == []


def test_get_document_chunks(client):
    """上传文档后可查询其 chunks。"""
    resp = _upload_md(client)
    doc_id = resp.json()["id"]

    resp = client.get(f"/documents/{doc_id}/chunks")
    assert resp.status_code == 200
    chunks = resp.json()
    assert len(chunks) >= 1
    # chunk 结构正确
    c = chunks[0]
    assert "id" in c
    assert "content" in c
    assert len(c["content"]) > 0


def test_get_chunks_nonexistent(client):
    """查询不存在文档的 chunks 返回 404。"""
    resp = client.get("/documents/nonexistent-id/chunks")
    assert resp.status_code == 404


def test_department_filter(client):
    """按部门筛选文档。"""
    # 不同部门上传
    _upload_md(client, "a.md", "# A\n\n部门A的文档。")
    client.post(
        "/documents/upload",
        files={"file": ("b.md", io.BytesIO(b"# B\n\nB department."), "text/markdown")},
        data={"department": "电气所"},
    )

    resp = client.get("/documents", params={"department": "结构所"})
    assert resp.status_code == 200
    docs = resp.json()
    assert all(d["department"] == "结构所" for d in docs)

    resp = client.get("/documents", params={"department": "电气所"})
    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) >= 1
    assert all(d["department"] == "电气所" for d in docs)
