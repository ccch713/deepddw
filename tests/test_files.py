"""R4-6（DSH for Teams）：文件库测试。

验收：upload/list/download 可用；路径穿越防护；大小限制；solo 无 shared。
"""

from __future__ import annotations

import os

os.environ.setdefault("DDW_ACCESS_TOKEN", "test-files-token")

import pytest  # noqa: E402

from core.api import files as files_api  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    """独立文件根目录 + 默认 solo。"""
    monkeypatch.setenv("DDW_FILES_ROOT", str(tmp_path / "files"))
    monkeypatch.setattr("core.config.get_deployment_mode", lambda: "solo")
    yield


def test_solo_no_shared():
    """solo 模式：无共享目录（_resolve_dir 拒绝 is_shared）。"""
    with pytest.raises(ValueError):
        files_api._resolve_dir(is_shared=True)
    # 个人目录存在
    d = files_api._resolve_dir("m-TEST0001")
    assert d.name == "member:m-TEST0001"
    d2 = files_api._resolve_dir()  # 无 member_id → personal
    assert d2.name == "personal"


def test_upload_list_download(monkeypatch, tmp_path):
    """上传 → 列表 → 下载。"""
    r = files_api.upload_file("测试文档.txt", "hello world".encode(), "m-TEST0001")
    assert r["ok"] is True
    lst = files_api.list_files("m-TEST0001")
    assert any(f["name"] == "测试文档.txt" for f in lst["files"])
    p = files_api.download_file("测试文档.txt", "m-TEST0001")
    assert p is not None and p.read_text() == "hello world"


def test_path_traversal_blocked():
    """路径穿越防护（../ 拒绝）。"""
    r = files_api.upload_file("../../etc/passwd", b"x")
    assert r["ok"] is False
    assert files_api.download_file("../../etc/passwd") is None
    # 特殊字符拒绝
    r2 = files_api.upload_file("a/b", b"x")
    assert r2["ok"] is False


def test_size_limit(monkeypatch, tmp_path):
    """大小限制（max_size_mb 可配）。"""
    monkeypatch.setenv("DDW_FILES_MAX_MB", "1")  # 1MB
    big = b"x" * (1024 * 1024 + 10)
    r = files_api.upload_file("big.bin", big, "m-TEST0002")
    assert r["ok"] is False and "超过" in r["note"]


def test_shared_in_team(monkeypatch, tmp_path):
    """team 模式：shared + 个人并存。"""
    monkeypatch.setattr("core.config.get_deployment_mode", lambda: "team")
    r = files_api.upload_file("团队文件.txt", b"team", is_shared=True)
    assert r["ok"] is True
    lst = files_api.list_files(is_shared=True)
    assert any(f["name"] == "团队文件.txt" for f in lst["files"])
    # 个人目录独立
    r2 = files_api.upload_file("个人文件.txt", b"me", "m-TEST0003")
    assert r2["ok"] is True
    lst_shared = files_api.list_files(is_shared=True)["files"]
    lst_me = files_api.list_files("m-TEST0003")["files"]
    assert all(f["name"] != "个人文件.txt" for f in lst_shared)
    assert any(f["name"] == "个人文件.txt" for f in lst_me)


async def test_files_api_endpoints(client, monkeypatch, tmp_path):
    """HTTP：upload/list/download + 401 门禁。"""
    monkeypatch.setenv("DDW_FILES_ROOT", str(tmp_path / "files"))
    monkeypatch.setattr("core.config.get_deployment_mode", lambda: "solo")
    headers = {"X-DDW-Token": os.environ["DDW_ACCESS_TOKEN"]}
    r = await client.post("/api/v1/files/upload", headers=headers,
                          files={"file": ("a.txt", b"abc", "text/plain")})
    assert r.status_code == 200 and r.json()["data"]["ok"]
    r2 = await client.get("/api/v1/files/list", headers=headers)
    assert r2.status_code == 200
    assert any(f["name"] == "a.txt" for f in r2.json()["data"]["files"])
    r3 = await client.get("/api/v1/files/download/a.txt", headers=headers)
    assert r3.status_code == 200 and r3.content == b"abc"
    # 无 Token → 401
    r4 = await client.get("/api/v1/files/list")
    assert r4.status_code == 401
