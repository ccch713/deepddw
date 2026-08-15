"""P4 跨机授权广播 Broker 测试。

覆盖：
1. 配置禁用 → 不拉取
2. 服务端签名校验：正确通过 / 错误令牌 / 过期时间戳 / 错误签名拒绝
3. broker/state 端点：200 返回权威 state / 401 / 未启用 404
4. 客户端拉取 + sync_from_broker 覆盖本机 state
5. TTL 缓存：TTL 内不重复请求
6. Broker 不可达 → 回退缓存不抛异常
"""

from __future__ import annotations

import hashlib
import hmac
import time
from pathlib import Path

import pytest

from core.config import Settings
from core.utils.license_broker import (
    BROKER_STATE_PATH,
    HEADER_SIG,
    HEADER_TOKEN,
    HEADER_TS,
    _reset_cache,
    pull_authoritative_state,
    state_version,
    sync_from_broker,
    verify_broker_request,
)

TOKEN = "test-broker-token"
OLD_KEY = "LIC-OLD-001"
NEW_KEY = "LIC-NEW-002"


def _sig(ts: str, path: str = BROKER_STATE_PATH, token: str = TOKEN) -> str:
    return hmac.new(
        token.encode("utf-8"), f"{ts}:{path}".encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _enable_broker(monkeypatch, tmp_path, **overrides) -> None:
    """启用 broker 配置（settings 指向 tmp）。"""
    cfg = {
        "enabled": True,
        "url": "http://auth-node:8500",
        "token": TOKEN,
        "ttl_seconds": 60,
    }
    cfg.update(overrides)
    monkeypatch.setattr(
        "core.config._settings",
        Settings(raw={"license": {"broker": cfg}}),
    )


def _fake_transport(state: dict):
    """返回返回指定 state 的 MockTransport（带请求计数）。"""
    import httpx

    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        payload = {"code": 0, "data": {"state": state, "version": state_version(state)}}
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler), calls


def _err_transport(exc: Exception):
    import httpx

    def handler(request):
        raise exc

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# 1. 配置与签名校验
# ---------------------------------------------------------------------------


def test_broker_disabled_no_pull(monkeypatch, tmp_path):
    """未启用 → 拉取返回空，不发请求。"""
    monkeypatch.setattr(
        "core.config._settings",
        Settings(raw={"license": {"broker": {"enabled": False}}}),
    )
    _reset_cache()
    assert pull_authoritative_state() == {}


def test_verify_broker_request_ok(monkeypatch):
    """正确令牌 + 新鲜时间戳 + 正确签名 → 通过。"""
    _enable_broker(monkeypatch, None)
    ts = str(int(time.time()))
    assert verify_broker_request(TOKEN, ts, _sig(ts), BROKER_STATE_PATH) is True


def test_verify_broker_request_rejections(monkeypatch):
    """错误令牌 / 过期时间戳 / 错误签名 → 拒绝。"""
    _enable_broker(monkeypatch, None)
    ts = str(int(time.time()))
    assert verify_broker_request("wrong", ts, _sig(ts), BROKER_STATE_PATH) is False
    stale = str(int(time.time()) - 3600)
    assert verify_broker_request(TOKEN, stale, _sig(stale), BROKER_STATE_PATH) is False
    assert verify_broker_request(TOKEN, ts, "deadbeef", BROKER_STATE_PATH) is False
    assert verify_broker_request("", ts, "", BROKER_STATE_PATH) is False


# ---------------------------------------------------------------------------
# 2. broker/state 端点
# ---------------------------------------------------------------------------


def _build_app():
    from fastapi import FastAPI

    from core.api.license import router as lic_router

    app = FastAPI()
    app.include_router(lic_router)
    return app


async def test_broker_state_endpoint_ok(monkeypatch, tmp_path):
    """签名请求 → 200 返回权威 state。"""
    from httpx import ASGITransport, AsyncClient

    _enable_broker(monkeypatch, tmp_path)
    from core.utils.license_state import replace_state

    # 让权威 state 读取指向 tmp（而非默认 ./data/）
    monkeypatch.setattr(
        "core.utils.license_state._state_path",
        lambda: tmp_path / "license_state.json",
    )
    replace_state(
        {"active_license_key": OLD_KEY, "superseded_by": NEW_KEY},
        path=tmp_path / "license_state.json",
    )

    app = _build_app()
    ts = str(int(time.time()))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            BROKER_STATE_PATH,
            headers={HEADER_TOKEN: TOKEN, HEADER_TS: ts, HEADER_SIG: _sig(ts)},
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["state"]["superseded_by"] == NEW_KEY
    assert data["version"] == state_version(data["state"])


async def test_broker_state_endpoint_unauthorized_and_disabled(monkeypatch, tmp_path):
    """错误签名 401；未启用 404。"""
    from httpx import ASGITransport, AsyncClient

    _enable_broker(monkeypatch, tmp_path)
    app = _build_app()
    ts = str(int(time.time()))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        bad = await ac.get(
            BROKER_STATE_PATH,
            headers={HEADER_TOKEN: TOKEN, HEADER_TS: ts, HEADER_SIG: "bad"},
        )
        assert bad.status_code == 401
        assert "校验失败" in bad.json()["detail"]

    # 未启用 → 404
    monkeypatch.setattr(
        "core.config._settings",
        Settings(raw={"license": {"broker": {"enabled": False}}}),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        off = await ac.get(BROKER_STATE_PATH)
        assert off.status_code == 404


# ---------------------------------------------------------------------------
# 3. 客户端拉取 / 覆盖 / TTL / 回退
# ---------------------------------------------------------------------------


def test_pull_and_sync_from_broker(monkeypatch, tmp_path):
    """拉取权威 state → sync_from_broker 覆盖本机 license_state.json。"""
    _enable_broker(monkeypatch, tmp_path)
    transport, _ = _fake_transport(
        {"active_license_key": OLD_KEY, "superseded_by": NEW_KEY}
    )
    _reset_cache()

    from core.utils.license_state import load_license_state

    # 本机初始 state（无替换记录）
    from core.utils.license_state import replace_state as rs

    rs({"active_license_key": OLD_KEY}, path=tmp_path / "license_state.json")
    monkeypatch.setattr(
        "core.utils.license_state._state_path",
        lambda: tmp_path / "license_state.json",
    )

    ok = sync_from_broker(force=True, transport=transport)
    assert ok is True
    local = load_license_state(path=tmp_path / "license_state.json")
    assert local["superseded_by"] == NEW_KEY  # 已覆盖为权威值


def test_pull_ttl_cache(monkeypatch, tmp_path):
    """TTL 内第二次拉取不重复请求。"""
    _enable_broker(monkeypatch, tmp_path)
    transport, calls = _fake_transport({"active_license_key": OLD_KEY})
    _reset_cache()

    pulled = pull_authoritative_state(force=True, transport=transport)
    assert pulled["active_license_key"] == OLD_KEY
    pulled2 = pull_authoritative_state(transport=transport)  # TTL 内
    assert pulled2["active_license_key"] == OLD_KEY
    assert calls["n"] == 1  # 只请求一次


def test_pull_unreachable_falls_back(monkeypatch, tmp_path, caplog):
    """Broker 不可达 → 返回缓存/空，不抛异常。"""
    import logging

    _enable_broker(monkeypatch, tmp_path)
    _reset_cache()
    err_transport = _err_transport(RuntimeError("connection refused"))

    with caplog.at_level(logging.WARNING, logger="core.utils.license_broker"):
        result = pull_authoritative_state(force=True, transport=err_transport)
    assert result == {}  # 无缓存 → 空，调用方 fail-closed
    assert any("pull failed" in r.message for r in caplog.records)


def test_state_version_changes_with_content():
    """state 内容变化 → version 变化。"""
    v1 = state_version({"active_license_key": OLD_KEY})
    v2 = state_version({"active_license_key": OLD_KEY, "superseded_by": NEW_KEY})
    assert v1 != v2
    assert len(v1) == 16


# ---------------------------------------------------------------------------
# 第二批：数据同步捎带广播（check_sync_allowed 前自动拉取权威 state）
# ---------------------------------------------------------------------------


def test_check_sync_allowed_pulls_broker_before_check(monkeypatch, tmp_path):
    """配置 Broker 后：拦截判定前自动拉取权威 state 并覆盖本机 → 旧码超期被拒。

    模拟克隆容器：本机 state 是干净旧快照（无替换记录），Broker 权威 state
    已记录 L1→L2 超期。仅调用 check_sync_allowed（数据同步入口）即完成捎带。
    """
    from core.utils.license_state import (
        check_sync_allowed,
        load_license_state,
        replace_state,
    )

    _enable_broker(monkeypatch, tmp_path)
    state_path = tmp_path / "license_state.json"
    monkeypatch.setattr("core.utils.license_state._state_path", lambda: state_path)
    # 本机：干净旧快照（无替换记录）
    replace_state({"active_license_key": OLD_KEY}, path=state_path)
    # Broker 权威：L1 → L2 超期
    from datetime import datetime, timedelta, timezone

    auth = {
        "active_license_key": OLD_KEY,
        "superseded_by": NEW_KEY,
        "superseded_at": datetime.now(timezone.utc).isoformat(),
        "grace_ends_at": (
            datetime.now(timezone.utc) - timedelta(days=1)
        ).isoformat(),
    }
    transport, calls = _fake_transport(auth)
    _reset_cache()
    monkeypatch.setattr(
        "core.utils.license_broker.pull_authoritative_state",
        lambda **kw: pull_authoritative_state(force=True, transport=transport),
    )

    allowed, reason = check_sync_allowed(OLD_KEY, path=state_path)
    assert calls["n"] == 1  # 捎带拉取发生
    local = load_license_state(path=state_path)
    assert local["superseded_by"] == NEW_KEY  # 本机已被权威广播覆盖
    assert allowed is False
    assert reason == "授权已更新，请联系经销商获取新授权码"


# ---------------------------------------------------------------------------
# 数据同步捎带补全：响应头携带 state version
# ---------------------------------------------------------------------------


async def test_broker_state_response_headers(monkeypatch, tmp_path):
    """broker/state 响应头捎带权威 state 版本与 superseded 状态。"""
    from httpx import ASGITransport, AsyncClient

    _enable_broker(monkeypatch, tmp_path)
    from core.utils.license_state import replace_state

    replace_state(
        {"active_license_key": OLD_KEY, "superseded_by": NEW_KEY},
        path=tmp_path / "license_state.json",
    )
    monkeypatch.setattr(
        "core.utils.license_state._state_path",
        lambda: tmp_path / "license_state.json",
    )

    app = _build_app()
    ts = str(int(time.time()))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            BROKER_STATE_PATH,
            headers={HEADER_TOKEN: TOKEN, HEADER_TS: ts, HEADER_SIG: _sig(ts)},
        )
    assert resp.status_code == 200
    assert "x-ddw-license-state-version" in resp.headers
    assert resp.headers["x-ddw-license-superseded"] == "true"
    assert resp.headers["x-ddw-license-state-version"] == state_version(
        resp.json()["data"]["state"]
    )


async def test_upload_response_headers_carry_state(tmp_path, monkeypatch):
    """数据同步拦截点（upload）响应头捎带本机 state 版本（模板示范）。"""
    import json

    from core.config import Settings
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    monkeypatch.setattr(
        "core.config._settings",
        Settings(
            raw={
                "license": {
                    "cache_path": str(tmp_path / "license_cache.json")
                }
            }
        ),
    )
    from plugins.ddw_knowledge_hierarchy.router import router as kh_router

    app = FastAPI()
    app.include_router(kh_router, prefix="/api/v1/plugins/ddw-knowledge-hierarchy")
    transport = ASGITransport(app=app)

    # 主系统 state：L1 被替换且超期 → 403 路径（403 响应同样携带捎带头）
    from datetime import datetime, timedelta, timezone

    from core.utils.license_state import STATE_KEY_ENV as _SKE
    from core.utils.license_state import _sign_state, supersede

    monkeypatch.setenv(_SKE, "test-upload-state-key")
    state_path = tmp_path / "license_state.json"
    state = supersede(OLD_KEY, NEW_KEY, path=state_path)
    state["grace_ends_at"] = (
        datetime.now(timezone.utc) - timedelta(days=1)
    ).isoformat()
    state_path.write_text(
        json.dumps({"data": state, "sig": _sign_state(state)}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "license_cache.json").write_text(
        json.dumps({"license_key": OLD_KEY, "customer": "t"}), encoding="utf-8"
    )
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/plugins/ddw-knowledge-hierarchy/documents/upload",
            headers={"X-DDW-License-Key": OLD_KEY},
            files={"file": ("note.md", b"# t\ncontent", "text/markdown")},
        )
    assert resp.status_code == 403
    assert resp.headers["x-ddw-license-superseded"] == "true"
    assert resp.headers["x-ddw-license-state-version"] == state_version(state)


# ---------------------------------------------------------------------------
# P4 热加载：PluginRuntime + 管理端点（红线测试）
# ---------------------------------------------------------------------------


@pytest.fixture
def isolate_plugins():
    """隔离真实 plugins 包：runtime 测试用 tmp 假插件根。"""
    import sys

    saved = {
        k: sys.modules[k]
        for k in list(sys.modules)
        if k == "plugins" or k.startswith("plugins.")
    }
    for k in list(saved):
        del sys.modules[k]
    yield
    for k in list(sys.modules):
        if k == "plugins" or k.startswith("plugins."):
            del sys.modules[k]
    sys.modules.update(saved)


def _make_tmp_plugin(tmp_path, name: str, tier: str = "free", status: str = "") -> Path:
    d = tmp_path / "plugins" / name
    d.mkdir(parents=True, exist_ok=True)
    (tmp_path / "plugins" / "__init__.py").write_text("", encoding="utf-8")
    status_line = f"status: {status}\n" if status else ""
    (d / "manifest.yaml").write_text(
        f"name: {name}\nlicense: {tier}\n{status_line}version: 1.0.0\nconfig: {{}}\n",
        encoding="utf-8",
    )
    (d / "plugin.py").write_text(
        "class Plugin:\n    def __init__(self, app, config=None, manifest=None):\n"
        "        self.app = app\n        self.manifest = manifest or {}\n",
        encoding="utf-8",
    )
    return d


def test_runtime_load_one_and_registry(tmp_path, isolate_plugins):
    """热加载：load_one 加载插件并登记 registry。"""
    import sys

    from core.plugin_manager.runtime import PluginRuntime

    _make_tmp_plugin(tmp_path, "hot_plugin")
    sys.path.insert(0, str(tmp_path))
    rt = PluginRuntime(
        plugin_root=tmp_path / "plugins",
        audit_path=tmp_path / "audit.jsonl",
    )
    instance = rt.load_one("hot_plugin", operator="test")
    assert instance is not None
    rec = rt.registry.get("hot_plugin")
    assert rec["state"] == "loaded"
    assert rec["manifest"]["license"] == "free"
    # 审计写入
    audit = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "load" in audit and "hot_plugin" in audit


def test_runtime_locked_rejected(tmp_path):
    """红线③：locked 插件热装拒绝。"""
    import sys

    from core.plugin_manager.runtime import PluginRuntime

    _make_tmp_plugin(tmp_path, "locked_plugin", status="locked")
    sys.path.insert(0, str(tmp_path))
    rt = PluginRuntime(
        plugin_root=tmp_path / "plugins",
        audit_path=tmp_path / "audit.jsonl",
    )
    assert rt.load_one("locked_plugin", operator="test") is None
    assert rt.registry.get("locked_plugin") is None


def test_runtime_unlicensed_commercial_rejected(tmp_path, monkeypatch):
    """红线②：未授权 commercial 插件热装拒绝（fail-closed 语义一致）。"""
    import sys

    from core.config import Settings
    from core.plugin_manager.runtime import PluginRuntime

    _make_tmp_plugin(tmp_path, "commercial_plugin", tier="commercial")
    sys.path.insert(0, str(tmp_path))
    monkeypatch.setenv("DDW_ENV", "production")
    # 无 license 文件 → 生产 fail-closed → authorized=[]
    rt = PluginRuntime(
        plugin_root=tmp_path / "plugins",
        audit_path=tmp_path / "audit.jsonl",
        settings=Settings(
            raw={
                "license": {"cache_path": str(tmp_path / "license_cache.json")},
                "plugins": {"root_dir": str(tmp_path / "plugins")},
            }
        ),
    )
    assert rt.load_one("commercial_plugin", operator="test") is None
    audit = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "not licensed" in audit or "not in license" in audit


def test_runtime_unload_and_reload(tmp_path, isolate_plugins):
    """停用入口 + 滚动重挂。"""
    import sys

    from core.plugin_manager.runtime import PluginRuntime

    _make_tmp_plugin(tmp_path, "reload_plugin")
    sys.path.insert(0, str(tmp_path))
    rt = PluginRuntime(
        plugin_root=tmp_path / "plugins",
        audit_path=tmp_path / "audit.jsonl",
    )
    assert rt.load_one("reload_plugin", operator="test") is not None
    assert rt.unload_entry("reload_plugin", operator="test") is True
    assert rt.registry.get("reload_plugin")["state"] == "disabled"
    assert rt.reload_one("reload_plugin", operator="test") is True
    assert rt.registry.get("reload_plugin")["state"] == "loaded"


# ---------------------------------------------------------------------------
# P4 管理端点集成（install/load/unload/reload/runtime + 权限）
# ---------------------------------------------------------------------------


def _admin_app_with_runtime(tmp_path, monkeypatch):
    """构造挂载 admin router + PluginRuntime 的 mini app。"""
    from fastapi import FastAPI

    from core.api.admin import router as admin_router

    app = FastAPI()
    app.include_router(admin_router)
    from core.plugin_manager.runtime import PluginRuntime

    app.state.plugin_runtime = PluginRuntime(
        app=app,
        plugin_root=tmp_path / "plugins",
        audit_path=tmp_path / "audit.jsonl",
    )
    monkeypatch.setenv("DDW_ENV", "production")
    return app


def _super_token() -> str:
    from core.auth.jwt import create_access_token

    return create_access_token(user_id=1, tenant_id=1, role="superadmin")


async def test_admin_runtime_endpoints(tmp_path, monkeypatch, isolate_plugins):
    """runtime/load/unload/reload 端点全链路（superadmin）。"""
    import sys

    from httpx import ASGITransport, AsyncClient

    _make_tmp_plugin(tmp_path, "api_plugin")
    sys.path.insert(0, str(tmp_path))
    app = _admin_app_with_runtime(tmp_path, monkeypatch)
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {_super_token()}"}

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 空 runtime 快照
        snap = await ac.get("/api/v1/admin/plugins/runtime", headers=headers)
        assert snap.status_code == 200
        # load（安装即生效路径：插件已落盘，直接热启）
        r = await ac.post("/api/v1/admin/plugins/api_plugin/load", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["state"] == "loaded"
        # 快照含插件
        snap2 = await ac.get("/api/v1/admin/plugins/runtime", headers=headers)
        names = [i["name"] for i in snap2.json()["items"]]
        assert "api_plugin" in names
        # unload
        r2 = await ac.post("/api/v1/admin/plugins/api_plugin/unload", headers=headers)
        assert r2.status_code == 200 and r2.json()["state"] == "disabled"
        # reload（有旧实例 → pending_restart）
        r3 = await ac.post("/api/v1/admin/plugins/api_plugin/reload", headers=headers)
        assert r3.status_code == 200, r3.text
        assert r3.json()["reloaded"] is True
        assert r3.json()["pending_restart"] is True


async def test_admin_runtime_forbidden(tmp_path, monkeypatch):
    """非 superadmin → 403（member 被 current_admin 拦 / owner 被 superadmin 拦）。"""
    from core.auth.jwt import create_access_token
    from httpx import ASGITransport, AsyncClient

    app = _admin_app_with_runtime(tmp_path, monkeypatch)
    transport = ASGITransport(app=app)
    member = create_access_token(user_id=2, tenant_id=1, role="member")
    owner = create_access_token(user_id=3, tenant_id=1, role="owner")

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r_member = await ac.post(
            "/api/v1/admin/plugins/x/load",
            headers={"Authorization": f"Bearer {member}"},
        )
        assert r_member.status_code == 403
        r_owner = await ac.post(
            "/api/v1/admin/plugins/x/load",
            headers={"Authorization": f"Bearer {owner}"},
        )
        assert r_owner.status_code == 403
        assert "仅超级管理员" in r_owner.json()["detail"]


async def test_admin_install_package_endpoint(tmp_path, monkeypatch, isolate_plugins):
    """install 端点：签名包上传 → 落盘 → 安装即生效（registry loaded）。"""
    import sys

    from httpx import ASGITransport, AsyncClient

    sys.path.insert(0, str(tmp_path))

    from core.plugin_manager import installer

    monkeypatch.setenv("DDW_PLUGIN_SIGNING_PUBLIC_KEY", "x" * 32)
    # 生成密钥对 + 签名包
    priv, pub_b64 = None, None
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv = Ed25519PrivateKey.generate()
    import base64 as _b64

    pub_b64 = _b64.b64encode(priv.public_key().public_bytes_raw()).decode()
    monkeypatch.setenv("DDW_PLUGIN_SIGNING_PUBLIC_KEY", pub_b64)
    (tmp_path / "plugins").mkdir(exist_ok=True)
    (tmp_path / "plugins" / "__init__.py").write_text("", encoding="utf-8")
    src = tmp_path / "src_plugin"
    src.mkdir(parents=True)
    (src / "manifest.yaml").write_text(
        "name: src_plugin\nlicense: free\nversion: 1.0.0\nconfig: {}\n",
        encoding="utf-8",
    )
    (src / "plugin.py").write_text(
        "class Plugin:\n"
        "    def __init__(self, app, config=None, manifest=None):\n"
        "        self.app = app\n",
        encoding="utf-8",
    )
    pkg = installer.sign_package(src, priv, tmp_path / "src_plugin.ddwplugin")

    app = _admin_app_with_runtime(tmp_path, monkeypatch)
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {_super_token()}"}

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/admin/plugins/install",
            headers=headers,
            files={
                "file": ("src_plugin.ddwplugin", pkg.read_bytes(), "application/zip")
            },
        )
    assert resp.status_code == 201, resp.text
    assert resp.json()["state"] == "loaded"
    assert (tmp_path / "plugins" / "src_plugin" / "manifest.yaml").exists()
