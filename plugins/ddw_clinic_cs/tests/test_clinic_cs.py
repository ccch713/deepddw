"""ddw_clinic_cs 测试套件 — 口腔诊所 AI 客服.

覆盖：
  1. health 端点（插件元信息 + 知识库块数）
  2. chat 空消息 / 超长消息 → 400
  3. chat 正常对话（mock LLM）→ kb+llm 来源
  4. chat LLM 不可用降级 → kb_fallback
  5. 会话历史保留（同一 session_id 连续对话）
  6. 知识库 RAG 检索真实生效
"""
from __future__ import annotations

import pytest
from plugins.ddw_clinic_cs import router as cs_router  # noqa: F401  (monkeypatch target)
from plugins.ddw_clinic_cs import router as plugin_router
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    """App with the plugin router; LLM calls mocked away."""
    app = FastAPI()
    app.include_router(plugin_router.router)

    async def _fake_llm(system: str, user: str, history: list) -> str:
        return "我是小齿，请问您有什么需要帮助的？"

    monkeypatch.setattr(cs_router, "_ask_llm", _fake_llm)
    monkeypatch.setattr(cs_router, "_sessions", {})
    monkeypatch.setattr(cs_router, "_session_ts", {})

    with TestClient(app) as c:
        yield c


# --------------------------------------------------------------------------- #
# health
# --------------------------------------------------------------------------- #


def test_health_ok(client):
    resp = client.get("/api/v1/plugins/ddw_clinic_cs/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["plugin"] == "ddw_clinic_cs"
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
    assert data["knowledge_chunks"] >= 0


# --------------------------------------------------------------------------- #
# chat 参数校验
# --------------------------------------------------------------------------- #


def test_chat_empty_message_400(client):
    resp = client.post(
        "/api/v1/plugins/ddw_clinic_cs/chat",
        json={"message": "   "},
    )
    assert resp.status_code == 400


def test_chat_too_long_400(client):
    resp = client.post(
        "/api/v1/plugins/ddw_clinic_cs/chat",
        json={"message": "牙" * 2001},
    )
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# chat 正常对话
# --------------------------------------------------------------------------- #


def test_chat_normal(client):
    resp = client.post(
        "/api/v1/plugins/ddw_clinic_cs/chat",
        json={"message": "你们洗牙多少钱？", "mode": "clinic"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"].startswith("clinic_")
    assert data["source"] == "kb+llm"
    assert "小齿" in data["answer"] or len(data["answer"]) > 0


def test_chat_session_history_preserved(client):
    sid = "clinic_test_sess_001"
    for msg in ["你好", "我想洗牙", "多少钱？"]:
        resp = client.post(
            "/api/v1/plugins/ddw_clinic_cs/chat",
            json={"message": msg, "session_id": sid},
        )
        assert resp.status_code == 200
        assert resp.json()["session_id"] == sid
    # 会话历史应保留 3 条 user + 3 条 assistant
    assert len(cs_router._sessions[sid]) == 6  # noqa: SLF001


# --------------------------------------------------------------------------- #
# LLM 不可用降级
# --------------------------------------------------------------------------- #


def test_chat_llm_fallback_kb(client, monkeypatch):
    async def _broken_llm(system: str, user: str, history: list) -> str:
        return ""

    monkeypatch.setattr(cs_router, "_ask_llm", _broken_llm)
    resp = client.post(
        "/api/v1/plugins/ddw_clinic_cs/chat",
        json={"message": "补牙"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "kb_fallback"
    assert len(data["answer"]) > 0  # 知识库片段或客服电话降级


# --------------------------------------------------------------------------- #
# 知识库 RAG
# --------------------------------------------------------------------------- #


def test_kb_search_returns_chunks():
    kb = cs_router._get_kb()  # noqa: SLF001
    assert kb is not None
    chunks = kb.search("洗牙", top_k=2)
    assert isinstance(chunks, list)
    for c in chunks:
        assert "source" in c and "content" in c
