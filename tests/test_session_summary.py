"""P1-3（multidevice）：会话跨设备续接（最近会话摘要）测试。

验收：手机端可列出最近 5 个会话摘要并打开续问（摘要按 workspace 过滤，
默认 shared 向后兼容；API Token 门禁）。
"""

from __future__ import annotations

import os

os.environ.setdefault("DDW_ACCESS_TOKEN", "test-session-summary-token")

import pytest  # noqa: E402

from core.knowledge import (  # noqa: E402
    reset_conn_pool,
    session_summary_list,
    session_summary_save,
)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    from core import knowledge as kb

    monkeypatch.setattr(kb, "_db_path", lambda: tmp_path / "kb.db")
    reset_conn_pool()
    yield
    reset_conn_pool()


def test_summary_save_and_list():
    """保存摘要 → 列出（同 session 覆盖；limit 生效）。"""
    session_summary_save(
        "sess-a-0001", "部署讨论", "决定用 Docker Compose 部署", "teamA",
    )
    session_summary_save("sess-a-0002", "记忆重构", "完成了分层记忆", "teamA")
    session_summary_save("sess-a-0003", "第三段", "内容三", "teamA")
    # 同 session 覆盖（不新增）
    session_summary_save("sess-a-0001", "部署讨论v2", "改为国内镜像加速", "teamA")

    results = session_summary_list(limit=5, workspace="teamA").get("results", [])
    assert len(results) == 3  # 覆盖后仍 3 条
    titles = {r["session_id"]: r["title"] for r in results}
    assert titles["sess-a-0001"] == "部署讨论v2"
    assert "国内镜像加速" in [
        r["summary"] for r in results if r["session_id"] == "sess-a-0001"
    ][0]


def test_summary_workspace_isolation():
    """摘要按 workspace 隔离（teamA 不见 teamB）。"""
    session_summary_save("sess-b-001", "团队A", "A 的内容", "teamA")
    session_summary_save("sess-b-002", "团队B", "B 的内容", "teamB")
    a = [r["session_id"] for r in session_summary_list(5, "teamA").get("results", [])]
    b = [r["session_id"] for r in session_summary_list(5, "teamB").get("results", [])]
    assert "sess-b-001" in a and "sess-b-002" not in a
    assert "sess-b-002" in b and "sess-b-001" not in b


def test_summary_shared_legacy_compat():
    """默认 shared（旧客户端）可见 shared 摘要。"""
    session_summary_save("sess-c-001", "共享会话", "共享摘要")
    results = session_summary_list().get("results", [])  # 不传 workspace
    assert any(r["session_id"] == "sess-c-001" for r in results)


async def test_summary_api(client, monkeypatch, tmp_path):
    """HTTP：保存 + 列出（Token 门禁；401 无 Token）。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    headers = {"X-DDW-Token": os.environ["DDW_ACCESS_TOKEN"]}
    r = await client.post("/api/v1/session-summary", headers=headers,
                          json={"session_id": "sess-http-01",
                                "title": "手机续问",
                                "summary": "摘要内容", "workspace": "shared"})
    assert r.status_code == 200 and r.json()["data"]["ok"]
    r2 = await client.get("/api/v1/session-summary", headers=headers,
                          params={"limit": 5})
    assert r2.status_code == 200
    data = r2.json()["data"]
    assert any(s["session_id"] == "sess-http-01" for s in data["results"])
    # 无 Token → 401
    r3 = await client.get("/api/v1/session-summary")
    assert r3.status_code == 401
