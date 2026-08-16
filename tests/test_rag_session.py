"""会话→文档闭环 + 自动 RAG 测试（#6 / #7）。

- #7 自动 RAG：chat 请求 rag 开关 → kb 命中拼入 system 上下文；无命中/关闭/故障降级
- #6 会话→文档：session-docs 建文档+关联、按会话列出、越权 401
"""

from __future__ import annotations

import os

os.environ.setdefault("DDW_ACCESS_TOKEN", "test-rag-session-token")

import pytest  # noqa: E402

from core.api.chat import _build_rag_context, _apply_rag  # noqa: E402
from core.llm_gateway.base import ChatMessage  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_kb_pool():
    """每个测试前清空知识库连接池（P1-15：池按库路径分池，防止跨测试污染）。"""
    from core.knowledge import reset_conn_pool

    reset_conn_pool()
    yield
    reset_conn_pool()


# ---------------------------------------------------------------------------
# #7 自动 RAG
# ---------------------------------------------------------------------------


def test_rag_context_empty_when_no_kb(monkeypatch, tmp_path):
    """知识库为空 → 空上下文（不阻塞）。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    ctx = _build_rag_context("不存在的检索词xyz")
    assert ctx["context"] == ""
    assert ctx["hits"] == []


def test_rag_context_includes_hits(monkeypatch, tmp_path):
    """kb 命中 → system 上下文含检索结果。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    from core.knowledge import kb_add_document

    kb_add_document("SPC 质量手册", "统计过程控制 SPC 用于生产质量监控。")
    ctx = _build_rag_context("SPC")
    assert ctx["hits"]
    assert "SPC" in ctx["context"]
    assert "知识库检索结果" in ctx["context"]


def test_apply_rag_off_keeps_messages(monkeypatch, tmp_path):
    """rag=False → 消息原样，不注入上下文。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    from core.knowledge import kb_add_document

    kb_add_document("部署手册", "deepDDW 部署需要 Docker。")
    msgs = [ChatMessage(role="user", content="如何部署")]
    payload = type("P", (), {"rag": False, "system": None, "message": "如何部署"})()
    rag = _apply_rag(msgs, payload)
    assert rag["hits"] == []
    assert len(msgs) == 1 and msgs[0].role == "user"


def test_apply_rag_on_injects_system_first(monkeypatch, tmp_path):
    """rag=True + 命中 → system 消息在最前且含 KB 内容。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    from core.knowledge import kb_add_document

    kb_add_document("部署手册", "deepDDW 部署需要 Docker。")
    msgs = [ChatMessage(role="system", content="你是助手"),
                        ChatMessage(role="user", content="部署")]
    payload = type("P", (), {"rag": True, "system": "你是助手", "message": "部署"})()
    rag = _apply_rag(msgs, payload)
    assert rag["hits"]
    assert msgs[0].role == "system"
    assert "知识库检索结果" in msgs[0].content
    assert "deepDDW 部署" in msgs[0].content or "部署" in msgs[0].content


# ---------------------------------------------------------------------------
# #6 会话→文档闭环（API 层）
# ---------------------------------------------------------------------------


async def test_session_doc_add_and_list(client, monkeypatch, tmp_path):
    """POST session-docs 建文档+关联；GET 按会话列出。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    token = {"X-DDW-Token": os.environ["DDW_ACCESS_TOKEN"]}

    resp = await client.post(
        "/api/v1/knowledge/session-docs",
        headers=token,
        json={
            "session_id": "sess-abc-1",
            "title": "对话产出文档",
            "content": "这是会话中生成的 markdown 文档正文",
            "kind": "chat",
        },
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["ok"] is True
    assert data["session_id"] == "sess-abc-1"

    # 按会话列出
    listing = await client.get(
        "/api/v1/knowledge/session-docs",
        headers=token,
        params={"session_id": "sess-abc-1"},
    )
    assert listing.status_code == 200
    items = listing.json()["data"]["results"]
    assert len(items) == 1
    assert items[0]["title"] == "对话产出文档"
    assert items[0]["kind"] == "chat"

    # 其它会话为空
    other = await client.get(
        "/api/v1/knowledge/session-docs",
        headers=token,
        params={"session_id": "sess-other"},
    )
    assert other.json()["data"]["results"] == []


async def test_session_doc_requires_auth(client):
    """无 Token → 401（LAN 免密测试默认关闭）。"""
    resp = await client.get(
        "/api/v1/knowledge/session-docs", params={"session_id": "x"}
    )
    assert resp.status_code == 401
    resp2 = await client.post("/api/v1/knowledge/session-docs", json={})
    assert resp2.status_code == 401


async def test_rag_chat_returns_rag_meta(client, monkeypatch, tmp_path):
    """POST /chat 带 rag → 响应含 rag 元信息（hits/degraded）。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    from core.api import chat as chat_mod
    from core.llm_gateway.base import ChatResponse

    async def fake_chat(messages, **kwargs):
        return ChatResponse(
            content="收到", model="deepseek-chat", provider="deepseek",
            finish_reason="stop",
        )

    monkeypatch.setattr(chat_mod, "llm_chat", fake_chat)
    resp = await client.post(
        "/api/v1/chat/",
        headers={"X-DDW-Token": os.environ["DDW_ACCESS_TOKEN"]},
        json={"message": "你好", "rag": True},
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["rag"]["enabled"] is True
    assert "hits" in body["rag"]
    assert "degraded" in body["rag"]


# ---------------------------------------------------------------------------
# MCP 工具：ddw.docs.save / ddw.session.docs（v2.1 会话→文档闭环）
# ---------------------------------------------------------------------------


async def test_mcp_docs_save_and_session_docs(monkeypatch, tmp_path):
    """MCP 工具：保存会话文档 + 按会话列出（真实 handler）。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    from core.mcp.server import get_mcp_server

    mcp = get_mcp_server()
    save = mcp.tools.get("ddw.docs.save")
    assert save is not None
    result = await save.handler(
        {
            "session_id": "sess-mcp-1",
            "title": "MCP 对话文档",
            "content": "这是通过 MCP 工具保存的文档",
        },
        {},
    )
    assert result["ok"] is True
    assert result["id"]

    listing = mcp.tools.get("ddw.session.docs")
    assert listing is not None
    listed = await listing.handler({"session_id": "sess-mcp-1"}, {})
    assert listed["results"]
    assert listed["results"][0]["title"] == "MCP 对话文档"


async def test_mcp_tools_whitelist_in_list(monkeypatch, tmp_path):
    """新工具在白名单 tools/list 中可见（core 白名单）。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    from core.mcp.server import get_mcp_server

    names = {t.name for t in get_mcp_server().public_tools()}
    assert "ddw.docs.save" in names
    assert "ddw.session.docs" in names
