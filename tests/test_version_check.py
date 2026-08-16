"""P2-3（multidevice）：版本/升级检查测试。

验收：/api/v1/version 返回 latest_version + update_available；GitHub 探测
失败降级（latest=null，不阻塞）；版本比较正确；缓存生效。
"""

from __future__ import annotations

import os

os.environ.setdefault("DDW_ACCESS_TOKEN", "test-version-check-token")

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch):
    """清版本缓存。"""
    import core.main as main_mod

    with main_mod._VERSION_LOCK:
        main_mod._VERSION_CACHE["latest"] = None
        main_mod._VERSION_CACHE["at"] = 0.0
    yield
    with main_mod._VERSION_LOCK:
        main_mod._VERSION_CACHE["latest"] = None
        main_mod._VERSION_CACHE["at"] = 0.0


def test_version_compare():
    """版本比较（0.1.0 < 0.2.0；v 前缀容忍）。"""
    from core.main import _ver_gt, _ver_key

    assert _ver_key("0.1.0") == (0, 1, 0)
    assert _ver_key("v0.2.0") == (0, 2, 0)
    assert _ver_gt("0.2.0", "0.1.0") is True
    assert _ver_gt("0.1.0", "0.1.0") is False
    assert _ver_gt("0.1.9", "0.2.0") is False


def test_latest_version_cache(monkeypatch):
    """GitHub 探测成功 + 缓存（TTL 内第二次命中不重复请求）。"""
    import core.main as main_mod

    calls = {"n": 0}

    def fake_urlopen(req, timeout=5):
        calls["n"] += 1
        import json as _json

        class FakeResp:
            def read(self):
                return _json.dumps({"tag_name": "v0.2.0"}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return FakeResp()

    monkeypatch.setattr(
        "urllib.request.urlopen", fake_urlopen,
    )
    with main_mod._VERSION_LOCK:
        main_mod._VERSION_CACHE["latest"] = None
        main_mod._VERSION_CACHE["at"] = 0.0
    v1 = main_mod._latest_version()
    v2 = main_mod._latest_version()  # 命中缓存
    assert v1 == "0.2.0" and v2 == "0.2.0"
    assert calls["n"] == 1


async def test_version_endpoint_update_available(client, monkeypatch):
    """/api/v1/version：latest 高于当前 → update_available=true。"""
    import core.main as main_mod

    monkeypatch.setattr(main_mod, "APP_VERSION", "0.1.0")
    monkeypatch.setattr(main_mod, "_latest_version", lambda: "0.2.0")
    resp = await client.get("/api/v1/version")
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == "0.1.0"
    assert data["latest_version"] == "0.2.0"
    assert data["update_available"] is True


async def test_version_endpoint_degraded(client, monkeypatch):
    """GitHub 探测失败 → latest=null + update_available=false（不阻塞）。"""
    import core.main as main_mod

    monkeypatch.setattr(main_mod, "_latest_version", lambda: None)
    resp = await client.get("/api/v1/version")
    assert resp.status_code == 200
    data = resp.json()
    assert data["latest_version"] is None
    assert data["update_available"] is False
    assert data["version"]  # 当前版本始终有
