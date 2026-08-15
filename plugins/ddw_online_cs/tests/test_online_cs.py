"""ddw_online_cs 测试套件 — 在线客服（售前/售后双模式）.

覆盖：
  1. health 端点（插件元信息 + 知识库块数）
  2. chat 空消息 / 超长消息 → 400
  3. chat 正常对话（mock LLM）→ kb+llm 来源 + 会话保留
  4. chat LLM 不可用降级 → kb_fallback
  5. knowledge 端点（调试用）
  6. 售前/售后关键词分类 _match_categories 纯逻辑
  7. 售后模式反馈日志 _log_feedback
"""
from __future__ import annotations

import pytest
from plugins.ddw_online_cs import router as cs_router  # noqa: F401  (monkeypatch target)
from plugins.ddw_online_cs import router as plugin_router
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    """App with the plugin router; LLM calls mocked away."""
    app = FastAPI()
    app.include_router(plugin_router.router)

    async def _fake_llm(system: str, user: str, history: list) -> str:
        return "您好，我是 DDW 在线客服，很高兴为您服务。"

    monkeypatch.setattr(cs_router, "_ask_llm", _fake_llm)
    monkeypatch.setattr(cs_router, "_sessions", {})
    monkeypatch.setattr(cs_router, "_session_ts", {})

    with TestClient(app) as c:
        yield c


# --------------------------------------------------------------------------- #
# health
# --------------------------------------------------------------------------- #


def test_health_ok(client):
    resp = client.get("/api/v1/plugins/ddw_online_cs/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["plugin"] == "ddw_online_cs"
    assert data["status"] == "ok"
    assert data["version"] == "2.0.0"
    assert data["knowledge_chunks"] >= 0


# --------------------------------------------------------------------------- #
# chat 参数校验
# --------------------------------------------------------------------------- #


def test_chat_empty_message_400(client):
    resp = client.post(
        "/api/v1/plugins/ddw_online_cs/chat",
        json={"message": ""},
    )
    assert resp.status_code == 400


def test_chat_too_long_400(client):
    resp = client.post(
        "/api/v1/plugins/ddw_online_cs/chat",
        json={"message": "好" * 2001},
    )
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# chat 正常对话
# --------------------------------------------------------------------------- #


def test_chat_normal_presales(client):
    resp = client.post(
        "/api/v1/plugins/ddw_online_cs/chat",
        json={"message": "你们有什么产品？", "mode": "presales"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"].startswith("cs_")
    assert data["source"] == "kb+llm"
    assert len(data["answer"]) > 0


def test_chat_session_history_preserved(client):
    sid = "cs_test_sess_001"
    for msg in ["在吗", "想了解ESG评估", "多少钱"]:
        resp = client.post(
            "/api/v1/plugins/ddw_online_cs/chat",
            json={"message": msg, "session_id": sid, "mode": "presales"},
        )
        assert resp.status_code == 200
        assert resp.json()["session_id"] == sid
    assert len(cs_router._sessions[sid]) == 6  # noqa: SLF001


# --------------------------------------------------------------------------- #
# LLM 不可用降级
# --------------------------------------------------------------------------- #


def test_chat_llm_fallback_kb(client, monkeypatch):
    async def _broken_llm(system: str, user: str, history: list) -> str:
        return ""

    monkeypatch.setattr(cs_router, "_ask_llm", _broken_llm)
    resp = client.post(
        "/api/v1/plugins/ddw_online_cs/chat",
        json={"message": "ESG报告"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "kb_fallback"
    assert len(data["answer"]) > 0


# --------------------------------------------------------------------------- #
# knowledge 调试端点
# --------------------------------------------------------------------------- #


def test_knowledge_endpoint(client):
    resp = client.get("/api/v1/plugins/ddw_online_cs/knowledge?q=ESG&top_k=2")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


# --------------------------------------------------------------------------- #
# 纯逻辑：售前/售后关键词分类
# --------------------------------------------------------------------------- #


def test_match_categories_presales():
    cats = cs_router._match_categories("presales", "产品报价多少")  # noqa: SLF001
    assert isinstance(cats, list)
    assert len(cats) <= 2


def test_match_categories_postsales():
    cats = cs_router._match_categories("postsales", "我要投诉")  # noqa: SLF001
    assert isinstance(cats, list)


# --------------------------------------------------------------------------- #
# 售后反馈日志
# --------------------------------------------------------------------------- #


def test_log_feedback_writes():
    """售后模式：投诉消息写入插件 feedback/YYYY-MM-DD.md，测试后清理."""
    import time as _time

    # 记录测试前已有的反馈文件，避免误删
    feedback_dir = (
        cs_router.Path(cs_router.__file__).resolve().parent / "feedback"
    )
    today = _time.strftime("%Y-%m-%d")
    fb_file = feedback_dir / f"{today}.md"
    existed_before = fb_file.exists()

    cs_router._log_feedback("我要投诉，服务态度太差", "cs_sess_fb_1")  # noqa: SLF001

    assert fb_file.exists()
    content = fb_file.read_text(encoding="utf-8")
    assert "cs_sess_fb_1" in content

    # 清理：恢复测试前状态
    if not existed_before:
        fb_file.unlink()
