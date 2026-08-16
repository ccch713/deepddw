"""分层记忆测试（借鉴 dsh-auto-memory：三层/注入/沉淀/反思/预算/迁移/降级）。"""

from __future__ import annotations

import os

os.environ.setdefault("DDW_ACCESS_TOKEN", "test-memory-layered-token")

import pytest  # noqa: E402

from core.knowledge import (  # noqa: E402
    memory_budget_status,
    memory_context_build,
    memory_log_append,
    memory_logs_recent,
    memory_maintain,
    memory_note_put,
    memory_reflect_save,
    memory_search_v2,
    memory_user_put,
    migrate_memory_entries,
    reset_conn_pool,
)


@pytest.fixture(autouse=True)
def _reset(monkeypatch, tmp_path):
    """每测试独立库 + 清连接。"""
    from core import knowledge as kb

    monkeypatch.setattr(kb, "_db_path", lambda: tmp_path / "kb.db")
    reset_conn_pool()
    yield
    reset_conn_pool()


def test_layered_write_and_read():
    """三层写入/读取隔离（user/notes/logs/reflections 各自独立）。"""
    assert memory_user_put("规则A", "值A")["ok"]
    assert memory_note_put("决策B", "值B", source="deepddw")["ok"]
    assert memory_log_append("日志C", auto=True)["ok"]
    assert memory_reflect_save("反思D")["ok"]

    ctx = memory_context_build()
    assert "规则A" in ctx["context"]
    assert "决策B" in ctx["context"]
    assert "日志C" in ctx["context"]
    assert "反思D" not in ctx["context"]  # 反思不注入，仅检索
    assert ctx["chars"] <= ctx["budget"] * 1.2  # 预算截断不超太多


def test_context_budget_truncation():
    """注入预算截断：超预算时保留头尾并标注省略。"""
    for i in range(30):
        memory_user_put(f"规则{i}", "x" * 300)
    ctx = memory_context_build(budget=500)
    assert ctx["chars"] <= 600  # 500 预算 + 包装开销
    assert "…(记忆注入按预算截断" in ctx["context"]


def test_logs_append_only_and_recent():
    """日志 append-only：多次追加都在，recent 按日期倒序。"""
    memory_log_append("第一条")
    memory_log_append("第二条", auto=True)
    logs = memory_logs_recent(days=1)["results"]
    assert len(logs) == 2
    contents = [r["content"] for r in logs]
    assert "第一条" in contents and "第二条" in contents


def test_reflect_save_overwrites_same_date():
    """反思同日期覆盖（UNIQUE ref_date）。"""
    memory_reflect_save("v1", style="生活化")
    memory_reflect_save("v2", style="专业")
    from core.knowledge import memory_reflect_get

    r = memory_reflect_get(__import__("datetime").date.today().strftime("%Y-%m-%d"))
    assert r["found"] and r["content"] == "v2" and r["style"] == "专业"


def test_search_v2_multi_layer_with_source():
    """分层检索：跨层命中且带来源标注。"""
    memory_user_put("偏好", "喜欢简洁回答")
    memory_note_put("部署", "deepDDW 用 Docker 部署")
    memory_log_append("今天修了部署问题")
    hits = memory_search_v2("部署 简洁", 10)["results"]
    layers = {h["layer"] for h in hits}
    assert "user" in layers
    assert "notes" in layers
    assert "logs" in layers
    for h in hits:
        assert "source" in h and h["source"]  # 来源标注必有


def test_budget_status_and_maintain():
    """预算统计 + 超限压缩归档（不丢数据）。"""
    memory_note_put("旧1", "x" * 100)
    memory_note_put("旧2", "x" * 100)
    status = memory_budget_status()
    assert "user" in status and "notes" in status and "over" in status
    # 强制超限场景：直接归档最旧（maintain 在 over 时归档）
    result = memory_maintain()
    assert "archived" in result


def test_migrate_preserves_data():
    """迁移：旧 memory_entries → 分层（分类正确、数据不丢）。"""
    from core.knowledge import memory_put

    memory_put("default", "user-key", "用户规则内容", ["user"])
    memory_put("default", "note-key", "笔记内容", ["note"])
    memory_put("default", "log-key", "日志内容", ["log"])
    result = migrate_memory_entries()
    assert result["total"] == 3
    assert result["user"] >= 1
    assert result["notes"] >= 1
    assert result["logs"] >= 1


def test_consolidate_rule_base():
    """自动沉淀基座：统计当日 auto 日志数（寒暄阈值由调用方控制）。"""
    from core.knowledge import memory_consolidate

    memory_log_append("要点一", auto=True)
    info = memory_consolidate(auto_consolidate_min_chars=60)
    assert info["ok"] and info["today_auto_count"] >= 1


# ---------------------------------------------------------------------------
# HTTP 端点 + MCP 工具（v2.1：分层记忆以官方接口/MCP 工具暴露）
# ---------------------------------------------------------------------------


async def test_memory_api_endpoints(client, monkeypatch, tmp_path):
    """分层记忆 HTTP 端点（user/notes/logs/context/reflect/budget/maintain）。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    headers = {"X-DDW-Token": os.environ["DDW_ACCESS_TOKEN"]}

    r = await client.post("/api/v1/memory/user", headers=headers,
                          json={"key": "语气", "value": "亲切"})
    assert r.status_code == 200 and r.json()["data"]["ok"]

    r = await client.post("/api/v1/memory/notes", headers=headers,
                          json={"key": "决策", "value": "用 MCP 接入"})
    assert r.status_code == 200 and r.json()["data"]["ok"]

    r = await client.post("/api/v1/memory/logs", headers=headers,
                          json={"content": "今天完成记忆分层", "auto": True})
    assert r.status_code == 200 and r.json()["data"]["ok"]

    r = await client.get("/api/v1/memory/context", headers=headers)
    assert r.status_code == 200
    assert "语气" in r.json()["data"]["context"]

    r = await client.get("/api/v1/memory/logs", headers=headers, params={"days": 1})
    assert r.status_code == 200 and r.json()["data"]["results"]

    r = await client.post("/api/v1/memory/reflect", headers=headers,
                          json={"content": "今天反思", "style": "auto"})
    assert r.status_code == 200 and r.json()["data"]["ok"]

    r = await client.get("/api/v1/memory/budget", headers=headers)
    assert r.status_code == 200 and "user" in r.json()["data"]

    r = await client.get("/api/v1/memory/search-v2", headers=headers,
                         params={"q": "记忆"})
    assert r.status_code == 200 and "layers" in r.json()["data"]


async def test_memory_api_requires_auth(client, tmp_path):
    """无 Token → 记忆端点 401。"""
    r = await client.get("/api/v1/memory/context")
    assert r.status_code == 401


async def test_mcp_memory_tools(monkeypatch, tmp_path):
    """MCP 记忆工具：context/consolidate/reflect/maintain/note/user/search-v2。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    from core.mcp.server import get_mcp_server

    mcp = get_mcp_server()
    for name in ("ddw.memory.context", "ddw.memory.consolidate",
                 "ddw.memory.reflect", "ddw.memory.maintain",
                 "ddw.memory.note", "ddw.memory.user",
                 "ddw.memory.search-v2"):
        assert mcp.tools.get(name) is not None, name

    note = await mcp.tools.get("ddw.memory.note").handler(
        {"key": "MCP笔记", "value": "通过工具写入"}, {})
    assert note["ok"] is True

    user = await mcp.tools.get("ddw.memory.user").handler(
        {"key": "MCP偏好", "value": "简明"}, {})
    assert user["ok"] is True

    cons = await mcp.tools.get("ddw.memory.consolidate").handler(
        {"content": "工具沉淀要点"}, {})
    assert cons["ok"] is True

    ctx = await mcp.tools.get("ddw.memory.context").handler({}, {})
    assert "MCP笔记" in ctx["content"][0]["text"]

    ref = await mcp.tools.get("ddw.memory.reflect").handler(
        {"content": "工具反思", "style": "auto"}, {})
    assert ref["ok"] is True

    sv = await mcp.tools.get("ddw.memory.search-v2").handler(
        {"query": "MCP"}, {})
    assert sv["results"]

    mt = await mcp.tools.get("ddw.memory.maintain").handler({}, {})
    assert "ok" in mt
