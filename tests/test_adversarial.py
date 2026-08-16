"""对抗性破坏测试（16G 测试设备 · 发布前强制门禁）。

覆盖：异常输入 / 越权 / 超大 payload / 恶意字符 / 损坏数据 / 并发 / 降级链。
任一失败即视为发布阻断。本文件在 16G 设备上执行（ssh 16g 部署后 pytest）。
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3

import pytest

os.environ.setdefault("DDW_ACCESS_TOKEN", "adversarial-test-token")

from core.main import app  # noqa: E402

_TOKEN = {"X-DDW-Token": os.environ["DDW_ACCESS_TOKEN"]}
_EXTERNAL = {"X-Forwarded-For": "8.8.8.8"}
_LAN = {"X-Forwarded-For": "192.168.1.7"}


# ---------------------------------------------------------------------------
# A. 越权（鉴权语义——对抗核心）
# ---------------------------------------------------------------------------


async def test_auth_no_token_401(client):
    for path in (
        "/api/v1/knowledge/search?q=x",
        "/api/v1/memory/put",
        "/api/v1/llm/config",
        "/api/v1/chat/",
        "/api/v1/knowledge/session-docs?session_id=x",
    ):
        r = await client.get(path) if "search" in path or "session-docs" in path else await client.post(path, json={})
        assert r.status_code == 401, f"{path} 无 Token 应 401"


async def test_auth_wrong_token_401(client):
    r = await client.get(
        "/api/v1/llm/config", headers={"X-DDW-Token": "wrong-token-000000"}
    )
    assert r.status_code == 401


async def test_auth_external_forged_401(client):
    """外网来源（伪造 X-Forwarded-For 公网 IP）无 Token → 401（不可用 LAN 免密绕过）。"""
    r = await client.get("/api/v1/llm/config", headers=_EXTERNAL)
    assert r.status_code == 401


async def test_auth_external_with_token_200(client):
    r = await client.get("/api/v1/llm/config", headers={**_EXTERNAL, **_TOKEN})
    assert r.status_code == 200


async def test_auth_lan_bypass_disabled_401(client, monkeypatch):
    """DDW_LAN_BYPASS=0：内网无 Token 也 401（安全关闭生效）。"""
    monkeypatch.setenv("DDW_LAN_BYPASS", "0")
    r = await client.get("/api/v1/llm/config", headers=_LAN)
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# B. 异常输入 / 恶意字符
# ---------------------------------------------------------------------------


async def test_malformed_json_422(client):
    """非 JSON body → 422（不 500）。"""
    r = await client.post(
        "/api/v1/chat/", headers=_TOKEN, content=b"{not-json"
    )
    assert r.status_code in (400, 422)


async def test_bidi_control_chars_in_chat(client, monkeypatch):
    """BiDi 控制字符（PDF/PPTX 攻击向量）入 chat 不崩。"""
    import core.api.chat as chat_mod
    from core.llm_gateway.base import ChatResponse

    async def fake_chat(messages, **kwargs):
        return ChatResponse(
            content="ok", model="m", provider="deepseek", finish_reason="stop"
        )

    monkeypatch.setattr(chat_mod, "llm_chat", fake_chat)
    evil = "正常文本\u202e反转部分\u202c结束"
    r = await client.post(
        "/api/v1/chat/", headers=_TOKEN, json={"message": evil, "rag": False}
    )
    assert r.status_code == 200


async def test_fts_injection_query(client, monkeypatch, tmp_path):
    """FTS5 MATCH 注入（特殊字符）→ 不 500、不注入。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    evil = '" OR 1=1 --'
    r = await client.get(
        "/api/v1/knowledge/search", headers=_TOKEN, params={"q": evil}
    )
    assert r.status_code == 200


async def test_sql_injection_strings(client, monkeypatch, tmp_path):
    """SQL 注入字符串进记忆/文档 → 不执行、不崩。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    evil = "'; DROP TABLE memory_entries; --"
    r = await client.post(
        "/api/v1/memory/put", headers=_TOKEN, json={"key": evil, "value": evil}
    )
    assert r.status_code == 200


async def test_oversized_payload_422(client):
    """超大 payload（超 Pydantic 上限）→ 422 而非 500。"""
    r = await client.post(
        "/api/v1/chat/", headers=_TOKEN, json={"message": "x" * 40_000, "rag": False}
    )
    assert r.status_code == 422


async def test_empty_body_422(client):
    r = await client.post("/api/v1/chat/", headers=_TOKEN, json={})
    assert r.status_code == 422


async def test_session_id_oversized_422(client):
    r = await client.get(
        "/api/v1/knowledge/session-docs",
        headers=_TOKEN,
        params={"session_id": "x" * 500},
    )
    assert r.status_code in (400, 422)


# ---------------------------------------------------------------------------
# C. 并发（race 破坏测试）
# ---------------------------------------------------------------------------


async def test_concurrent_memory_puts(client, monkeypatch, tmp_path):
    """50 并发 memory.put → 全部 200，无 500/无重复主键冲突。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")

    async def one(i: int):
        r = await client.post(
            "/api/v1/memory/put", headers=_TOKEN,
            json={"key": f"k-{i}", "value": f"v-{i}"},
        )
        return r.status_code

    results = await asyncio.gather(*[one(i) for i in range(50)])
    assert all(s == 200 for s in results), f"并发失败: {[s for s in results if s != 200]}"


async def test_concurrent_chat_history(client, monkeypatch, tmp_path):
    """并发 chat 落库 → 不崩（主键冲突降级不阻塞回复）。"""
    import core.api.chat as chat_mod
    from core.llm_gateway.base import ChatResponse

    async def fake_chat(messages, **kwargs):
        return ChatResponse(
            content="ok", model="m", provider="deepseek", finish_reason="stop"
        )

    monkeypatch.setattr(chat_mod, "llm_chat", fake_chat)

    async def one(i: int):
        r = await client.post(
            "/api/v1/chat/", headers=_TOKEN,
            json={"message": f"msg-{i}", "rag": False},
        )
        return r.status_code

    results = await asyncio.gather(*[one(i) for i in range(30)])
    assert all(s == 200 for s in results), f"并发 chat 失败: {[s for s in results if s != 200]}"


# ---------------------------------------------------------------------------
# D. 损坏数据 / 降级链
# ---------------------------------------------------------------------------


async def test_corrupted_db_degrades(client, monkeypatch, tmp_path):
    """损坏知识库文件 → kb 检索降级（degraded=True），不 500。"""
    db_file = tmp_path / "kb.db"
    db_file.write_bytes(b"not a sqlite database at all" * 100)
    monkeypatch.setattr("core.knowledge._db_path", lambda: db_file)

    r = await client.get(
        "/api/v1/knowledge/search", headers=_TOKEN, params={"q": "anything"}
    )
    assert r.status_code == 200
    assert r.json()["data"]["degraded"] is True


async def test_chat_without_llm_key_degrades(client, monkeypatch, tmp_path):
    """LLM 全通道不可用 → chat 返回降级提示而非 500（主流程不阻塞）。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    from core.llm_gateway import router as gw_router
    from core.llm_gateway.base import ChatResponse

    async def fail_chat(self, messages, **kwargs):
        return ChatResponse(
            content="[llm-router] all providers unavailable",
            model="", provider="", finish_reason="error",
        )

    monkeypatch.setattr(gw_router.LLMRouter, "chat", fail_chat)
    r = await client.post(
        "/api/v1/chat/", headers=_TOKEN, json={"message": "你好", "rag": False}
    )
    assert r.status_code == 200
    assert "conversation_id" in r.json()["data"]


async def test_rag_degrades_gracefully(client, monkeypatch, tmp_path):
    """RAG 故障（KB 损坏）→ 对话仍 200，rag.degraded=True。"""
    db_file = tmp_path / "kb.db"
    db_file.write_bytes(b"corrupt" * 50)
    monkeypatch.setattr("core.knowledge._db_path", lambda: db_file)
    import core.api.chat as chat_mod
    from core.llm_gateway.base import ChatResponse

    async def fake_chat(messages, **kwargs):
        return ChatResponse(
            content="ok", model="m", provider="deepseek", finish_reason="stop"
        )

    monkeypatch.setattr(chat_mod, "llm_chat", fake_chat)
    r = await client.post(
        "/api/v1/chat/", headers=_TOKEN, json={"message": "部署", "rag": True}
    )
    assert r.status_code == 200
    assert r.json()["data"]["rag"]["degraded"] is True
