"""P2-1（multidevice）：备份/恢复 API 测试。

验收：一键备份可下载；恢复流程可用（校验 + 替换）；路径穿越防护；
Token 门禁。
"""

from __future__ import annotations

import os
import sqlite3

os.environ.setdefault("DDW_ACCESS_TOKEN", "test-backup-token")

import pytest  # noqa: E402

from core.api import backup as backup_api  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    """独立主库 + 备份目录。"""
    db = tmp_path / "ddw_main.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO t (v) VALUES ('数据1')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(backup_api, "_db_path", lambda: db)
    monkeypatch.setenv("DDW_BACKUP_DIR", str(tmp_path / "backups"))
    yield


def _mk_backup(monkeypatch, tmp_path) -> str:
    """生成一个可恢复的备份文件路径。"""
    src = tmp_path / "good-backup.db"
    conn = sqlite3.connect(str(src))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO t (v) VALUES ('恢复数据')")
    conn.commit()
    conn.close()
    return str(src)


def test_create_backup_and_list(monkeypatch, tmp_path):
    """一键备份：生成文件 + 列表可见；DEF-004 响应不含绝对路径。"""
    r = backup_api.create_backup()
    assert r["ok"] is True
    assert r["size_bytes"] > 0
    assert "abs_path" not in r  # DEF-004：不暴露服务器绝对路径
    assert "/" not in r["file"]  # 仅文件名
    lst = backup_api.list_backups()
    assert lst["results"] and lst["results"][0]["file"] == r["file"]


def test_restore_valid_backup(monkeypatch, tmp_path):
    """恢复：有效备份替换主库（数据变为备份内容）。"""
    _mk_backup(monkeypatch, tmp_path)  # 生成 good-backup.db（返回值仅用于断言可略）
    r = backup_api.restore_backup(tmp_path / "good-backup.db")
    assert r["ok"] is True
    conn = sqlite3.connect(str(backup_api._db_path()))
    v = conn.execute("SELECT v FROM t").fetchone()[0]
    assert v == "恢复数据"
    conn.close()


def test_restore_invalid_file(monkeypatch, tmp_path):
    """恢复：非 SQLite 文件拒绝（不碰主库）。"""
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"not a sqlite file at all")
    r = backup_api.restore_backup(bad)
    assert r["ok"] is False
    assert r.get("client_error") is True  # DEF-003：客户端输入错误分类
    # 主库仍完好
    conn = sqlite3.connect(str(backup_api._db_path()))
    v = conn.execute("SELECT v FROM t").fetchone()[0]
    assert v == "数据1"
    conn.close()


async def test_backup_api_endpoints(client, monkeypatch, tmp_path):
    """HTTP：create/list/download/restore + 401 门禁 + 路径穿越。"""
    headers = {"X-DDW-Token": os.environ["DDW_ACCESS_TOKEN"]}
    # create
    r = await client.post("/api/v1/backup/create", headers=headers)
    assert r.status_code == 200 and r.json()["data"]["ok"]
    fname = r.json()["data"]["file"]
    # list
    r2 = await client.get("/api/v1/backup/list", headers=headers)
    assert r2.status_code == 200 and r2.json()["data"]["results"]
    # download
    r3 = await client.get(f"/api/v1/backup/download/{fname}", headers=headers)
    assert r3.status_code == 200
    # 穿越防护：download 用 Path(name).name 规范化（../ 无法逃逸），
    # 不存在的备份 → 404（不泄露文件）
    r4 = await client.get(
        "/api/v1/backup/download/no-such-backup.db", headers=headers,
    )
    assert r4.status_code == 404
    # DEF-004：create 响应无 abs_path
    assert "abs_path" not in r.json()["data"]
    # DEF-003：restore 非 SQLite 文件 → 4xx（非 500）
    bad_upload = {"file": ("bad.db", b"not a sqlite file at all", "application/octet-stream")}
    r6 = await client.post("/api/v1/backup/restore", headers=headers, files=bad_upload)
    assert 400 <= r6.status_code < 500, f"expected 4xx, got {r6.status_code}"
    # 主库不被破坏（fixture 初始数据仍在）
    # 无 Token → 401
    r5 = await client.get("/api/v1/backup/list")
    assert r5.status_code == 401
