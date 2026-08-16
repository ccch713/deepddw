"""P1-1（multidevice）：工作区隔离测试。

验收：两台设备选不同 workspace → 各自记忆互不可见；选 shared 与旧行为
一致；旧客户端（无 workspace 参数）不受影响；workspace 会话绑定生效。
"""

from __future__ import annotations

import os

os.environ.setdefault("DDW_ACCESS_TOKEN", "test-workspace-isolation-token")

import pytest  # noqa: E402

from core.knowledge import (  # noqa: E402
    memory_context_build,
    memory_log_append,
    memory_logs_recent,
    memory_note_put,
    memory_user_list,
    memory_user_put,
    reset_conn_pool,
)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    """独立库 + 清连接/工作区映射。"""
    from core import knowledge as kb
    from core.api import workspace as ws

    monkeypatch.setattr(kb, "_db_path", lambda: tmp_path / "kb.db")
    ws.reset_workspace_map()
    reset_conn_pool()
    yield
    ws.reset_workspace_map()
    reset_conn_pool()


# ---------------------------------------------------------------------------
# 记忆层隔离
# ---------------------------------------------------------------------------


def test_workspace_memory_isolation():
    """不同 workspace 记忆互不可见；shared 可见全部。"""
    memory_user_put("偏好", "喜欢中文", workspace="teamA")
    memory_user_put("偏好", "喜欢英文", workspace="teamB")
    memory_user_put("共享项", "大家可见", workspace="shared")

    a = memory_user_list("teamA").get("results", [])
    b = memory_user_list("teamB").get("results", [])
    s = memory_user_list("shared").get("results", [])

    a_vals = {r["key"]: r["value"] for r in a}
    b_vals = {r["key"]: r["value"] for r in b}
    assert a_vals.get("偏好") == "喜欢中文"
    assert b_vals.get("偏好") == "喜欢英文"
    # 严格隔离：teamA 不见 teamB 的偏好
    assert "偏好" not in b_vals or b_vals.get("偏好") == "喜欢英文"
    assert a_vals.get("偏好") != "喜欢英文"
    # shared 视图只含 shared 数据（不含 teamA/teamB 的偏好）
    s_keys = {r["key"] for r in s}
    assert "共享项" in s_keys
    assert "偏好" not in s_keys


def test_workspace_logs_isolation():
    """日志按 workspace 隔离。"""
    memory_log_append("团队A的日志", workspace="teamA")
    memory_log_append("团队B的日志", workspace="teamB")
    memory_log_append("共享日志", workspace="shared")

    a = [r["content"] for r in memory_logs_recent(days=1, workspace="teamA").get("results", [])]
    b = [r["content"] for r in memory_logs_recent(days=1, workspace="teamB").get("results", [])]
    s = [r["content"] for r in memory_logs_recent(days=1, workspace="shared").get("results", [])]

    assert "团队A的日志" in a and "团队B的日志" not in a
    assert "团队B的日志" in b and "团队A的日志" not in b
    assert "共享日志" in s and "团队A的日志" not in s


def test_workspace_context_build_filtered():
    """注入块按 workspace 组装（teamA 不含 teamB 内容）。"""
    memory_user_put("项目", "A项目进度", workspace="teamA")
    memory_user_put("项目", "B项目进度", workspace="teamB")
    ctx_a = memory_context_build(workspace="teamA").get("context", "")
    ctx_b = memory_context_build(workspace="teamB").get("context", "")
    assert "A项目进度" in ctx_a and "B项目进度" not in ctx_a
    assert "B项目进度" in ctx_b and "A项目进度" not in ctx_b


def test_legacy_default_shared_compat():
    """旧客户端（无 workspace 参数）→ 默认 shared，与旧行为一致。"""
    memory_user_put("老数据", "旧值")  # 不传 workspace
    memory_note_put("老笔记", "旧笔记值")
    results = memory_user_list().get("results", [])  # 默认 shared
    assert any(r["key"] == "老数据" for r in results)
    # 显式 shared 也能看到
    results_shared = memory_user_list("shared").get("results", [])
    assert any(r["key"] == "老数据" for r in results_shared)


# ---------------------------------------------------------------------------
# 会话绑定（workspace API）
# ---------------------------------------------------------------------------


def test_workspace_bind_and_resolve():
    """会话绑定：绑定后按会话取 workspace；未绑定 → shared。"""
    from core.api import workspace as ws

    r = ws.bind_session("sess-12345", "teamA")
    assert r["ok"] and r["workspace"] == "teamA"
    assert ws.get_workspace("sess-12345") == "teamA"
    # 未绑定 → shared（旧客户端零影响）
    assert ws.get_workspace("unknown-session") == "shared"
    assert ws.get_workspace(None) == "shared"
    # 非法 workspace 拒绝
    bad = ws.bind_session("sess-67890", "bad space!")
    assert bad["ok"] is False
    assert ws.get_workspace("sess-67890") == "shared"


async def test_workspace_bind_api(client, monkeypatch, tmp_path):
    """HTTP 端点：绑定 + 查询（Token 门禁）。"""
    monkeypatch.setattr("core.api.status._db_path", lambda: tmp_path / "devices.db")
    headers = {"X-DDW-Token": os.environ["DDW_ACCESS_TOKEN"]}
    r = await client.post("/api/v1/workspace/bind", headers=headers,
                          json={"session_id": "sess-http-01", "workspace": "teamC"})
    assert r.status_code == 200 and r.json()["data"]["ok"]
    r2 = await client.get("/api/v1/workspace/current",
                          headers=headers, params={"session_id": "sess-http-01"})
    assert r2.json()["data"]["workspace"] == "teamC"
    # 无 Token → 401
    r3 = await client.get("/api/v1/workspace/current", params={"session_id": "x"})
    assert r3.status_code == 401


async def test_device_register_workspace(client, monkeypatch, tmp_path):
    """设备注册带 workspace → 状态面板可见 workspace 字段。"""
    monkeypatch.setattr("core.api.status._db_path", lambda: tmp_path / "devices.db")
    from core.api import status as status_api

    with status_api._active_lock:
        status_api._active.clear()
    headers = {"X-DDW-Token": os.environ["DDW_ACCESS_TOKEN"]}
    r = await client.post("/api/v1/device/register", headers=headers,
                          json={"device_id": "device-ws-0001",
                                "device_name": "团队A手机", "workspace": "teamA"})
    assert r.status_code == 200 and r.json()["data"]["ok"]
    snap = await client.get("/api/v1/status", headers=headers)
    dev = [d for d in snap.json()["data"]["devices"] if d["device_id"] == "device-ws-0001"][0]
    assert dev["workspace"] == "teamA"
