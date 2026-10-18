"""v0.8.0（virtual-office）：虚拟办公室 API 测试。

验收：
- Token 门禁生效（无 Token → 401）；
- /api/v1/office/state 返回固定编制 8 席、每人有 state/note；
- view-only：响应体不含任何表内容原文字段（只有白名单短语）；
- 缺表/缺库不翻车（容错路径返回 away/idle 而非 500）。
"""

from __future__ import annotations

os_env_set = True  # conftest 已设 DDW_ACCESS_TOKEN
import os  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TOKEN = os.environ.get("DDW_ACCESS_TOKEN", "test-token-deepddw")

EXPECTED_STAFF = {
    "gateway", "chat", "memory", "kb", "llm", "distill", "backup", "relay",
}


@pytest.fixture()
def client():
    from core.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


def _get_state(client: TestClient):
    r = client.get("/api/v1/office/state", headers={"X-DDW-Token": TOKEN})
    assert r.status_code == 200
    body = r.json()
    return (body.get("data") or body)


def test_office_requires_token(client):
    r = client.get("/api/v1/office/state")
    assert r.status_code == 401


def test_office_state_shape(client):
    data = _get_state(client)
    residents = data["residents"]
    assert EXPECTED_STAFF.issubset(residents.keys()), residents.keys()
    for _sid, s in residents.items():
        assert s["state"] in {
            "idle", "working", "walking", "search", "doc",
            "celebrating", "upset", "sleeping", "alert", "away",
        }, (_sid, s)
        assert isinstance(s.get("note", ""), str)
    assert "digest" in data and "top" in data["digest"] and "fails" in data["digest"]
    assert "meta" in data


def test_office_view_only_whitelist(client, tmp_path, monkeypatch):
    """写一条含敏感原文的记忆，确认 state 响应不透出 value 原文。"""
    from core.api import office as office_mod

    secret = "SECRET-VALUE-should-never-leak-9527"
    db = tmp_path / "main.db"
    import sqlite3

    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE memory_entries (id INTEGER PRIMARY KEY, namespace TEXT,"
        " key TEXT, value TEXT, tags TEXT, created_at TEXT, updated_at TEXT)"
    )
    conn.execute(
        "INSERT INTO memory_entries (namespace,key,value,tags,created_at,updated_at)"
        " VALUES ('default','k',?, '', datetime('now'), datetime('now'))",
        (secret,),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(office_mod, "_db_path", lambda: db)
    office_mod._cache["data"] = None  # 失效缓存

    data = office_mod.office_snapshot()
    blob = str(data)
    assert secret not in blob
    assert data["residents"]["memory"]["state"] in {"doc", "idle"}


def test_office_tolerates_missing_tables(tmp_path, monkeypatch):
    """空库（无任何表）也不得 500。"""
    from core.api import office as office_mod

    db = tmp_path / "empty.db"
    import sqlite3

    sqlite3.connect(db).close()
    monkeypatch.setattr(office_mod, "_db_path", lambda: db)
    office_mod._cache["data"] = None

    data = office_mod.office_snapshot()
    assert EXPECTED_STAFF.issubset(data["residents"].keys())
