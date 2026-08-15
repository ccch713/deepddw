"""P3 对抗性验证修复测试（Attack 2/3/7/8 + 额外 A）。

覆盖：
- Fix 1（Attack 3）：DDW_ENV 未设置但有 license 文件 → 生产 fail-closed；
  未知 env 值 → fail-closed；显式 development 保持开发行为
- 额外 A：未配置公钥 → 明确报错（不再回退占位公钥）
- Fix 2（Attack 7）：license_state HMAC 签名、篡改检测 fail-closed、
  旧格式+配置密钥视为篡改、请求方 X-DDW-License-Key 主系统权威判定
- Fix 2（Attack 8）：签名模式并发写原子性
- Fix 3（Attack 2）：Docker 指纹宿主 machine-id + 容器 id 组合
"""

from __future__ import annotations

import json
import threading

import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.utils.license_state import (
    STATE_KEY_ENV,
    check_sync_allowed,
    supersede,
    sync_license_state,
)

OLD_KEY = "LIC-OLD-001"
NEW_KEY = "LIC-NEW-002"
STATE_KEY = "test-state-hmac-key"


@pytest.fixture(autouse=True)
def _isolate_plugins_package():
    """隔离真实的 ``plugins`` 包：load_plugins 测试用 tmp 假插件根，
    全量套件中真实包可能已被其他测试导入（sys.modules 污染），需临时卸载并在测后恢复。
    """
    import sys

    saved = {
        k: sys.modules[k]
        for k in list(sys.modules)
        if k == "plugins" or k.startswith("plugins.")
    }
    for k in list(saved):
        del sys.modules[k]
    try:
        yield
    finally:
        # 只清理测试注入的 tmp 假插件模块（free_plugin 等），
        # 保留本测试新加载的真实插件模块——避免后续插件测试重载导致
        # SQLAlchemy declarative 重复注册冲突。
        for k in list(sys.modules):
            if (k == "plugins" or k.startswith("plugins.")) and k not in saved:
                src = getattr(sys.modules[k], "__file__", "") or ""
                if "pytest" in src and ("private/var" in src or "/tmp" in src):
                    del sys.modules[k]
        sys.modules.update(saved)


def _make_plugin(tmp_path: Path, name: str, tier: str) -> None:
    d = tmp_path / "plugins" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.yaml").write_text(
        f"name: {name}\nlicense: {tier}\nversion: 1.0.0\nconfig: {{}}\n",
        encoding="utf-8",
    )
    (d / "plugin.py").write_text(
        "class Plugin:\n    def __init__(self, app, config=None, manifest=None):\n"
        "        self.app = app\n",
        encoding="utf-8",
    )


def _setup_loader(tmp_path, monkeypatch, license_payload, set_env: str | None = None):
    """搭 tmp 插件根 + 假 settings + license 文件；返回 load_plugins。"""
    from core.config import Settings
    from core.main import load_plugins

    _make_plugin(tmp_path, "free_plugin", "free")
    _make_plugin(tmp_path, "commercial_plugin", "commercial")
    (tmp_path / "plugins" / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))

    lic_path = tmp_path / "license_cache.json"
    if license_payload is not None:
        lic_path.write_text(
            json.dumps(license_payload, ensure_ascii=False), encoding="utf-8"
        )
    settings = Settings(
        raw={
            "plugins": {"root_dir": str(tmp_path / "plugins")},
            "license": {"cache_path": str(lic_path)},
        }
    )
    monkeypatch.setattr("core.main.get_settings", lambda: settings)
    if set_env is not None:
        monkeypatch.setenv("DDW_ENV", set_env)
    else:
        monkeypatch.delenv("DDW_ENV", raising=False)
    return load_plugins


def _tampered_license() -> dict:
    """一个验签必失败的 license 文件内容（模拟篡改/无效）。"""
    return {"license_key": OLD_KEY, "customer": "测试", "signature": "0" * 64}


# ---------------------------------------------------------------------------
# Fix 1（Attack 3）：DDW_ENV 门控默认不再 fail-open
# ---------------------------------------------------------------------------


def test_load_plugins_unset_env_with_license_fail_closed(tmp_path, monkeypatch, caplog):
    """未设置 DDW_ENV + 存在 license 文件 → 按生产 fail-closed（只加载 free）。"""
    load_plugins = _setup_loader(tmp_path, monkeypatch, _tampered_license())
    from fastapi import FastAPI

    loaded = load_plugins(FastAPI())
    assert "free_plugin" in loaded
    assert "commercial_plugin" not in loaded
    assert any("DDW_ENV not set" in r.message for r in caplog.records)


def test_load_plugins_unset_env_no_license_dev_mode(tmp_path, monkeypatch, caplog):
    """未设置 DDW_ENV + 无 license 文件 → 保持开发全量加载（不锁死开发）。"""
    load_plugins = _setup_loader(tmp_path, monkeypatch, license_payload=None)
    from fastapi import FastAPI

    loaded = load_plugins(FastAPI())
    assert "free_plugin" in loaded
    assert "commercial_plugin" in loaded
    assert any("no license in dev mode" in r.message for r in caplog.records)


def test_load_plugins_unknown_env_fail_closed(tmp_path, monkeypatch, caplog):
    """DDW_ENV 未知值 → critical 日志 + 按生产 fail-closed。"""
    load_plugins = _setup_loader(
        tmp_path, monkeypatch, _tampered_license(), set_env="weird"
    )
    from fastapi import FastAPI

    loaded = load_plugins(FastAPI())
    assert "free_plugin" in loaded
    assert "commercial_plugin" not in loaded
    assert any("not a known value" in r.message for r in caplog.records)


def test_load_plugins_explicit_development_overrides(tmp_path, monkeypatch):
    """显式 DDW_ENV=development + 无效 license → 全量加载（显式覆盖）。"""
    load_plugins = _setup_loader(
        tmp_path, monkeypatch, _tampered_license(), set_env="development"
    )
    from fastapi import FastAPI

    loaded = load_plugins(FastAPI())
    assert "free_plugin" in loaded
    assert "commercial_plugin" in loaded


# ---------------------------------------------------------------------------
# 额外 A：未配置公钥 → 明确报错（不再回退占位公钥）
# ---------------------------------------------------------------------------


def test_missing_public_key_clear_error(tmp_path, monkeypatch):
    """有效签名的 license + 无公钥配置 → validate 明确报"未配置许可证公钥"。"""
    import base64

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from core.utils.license_validator import validate_license_file

    monkeypatch.delenv("DDW_LICENSE_PUBLIC_KEY", raising=False)
    monkeypatch.setattr("core.config._settings", None)  # 无 config 公钥

    priv = Ed25519PrivateKey.generate()
    payload = {
        "license_key": "LIC-P3-001",
        "customer": "测试",
        "instance_id": "i",
        "machine_fingerprint": "a" * 32,
        "valid_from": datetime.now(timezone.utc).date().isoformat(),
        "valid_to": (
            datetime.now(timezone.utc).date() + timedelta(days=30)
        ).isoformat(),
        "authorized_plugins": ["*"],
        "issued_by": "test",
        "license_format_version": 2,
        "sig_algo": "ed25519",
    }
    message = json.dumps(
        {k: v for k, v in payload.items() if k != "signature"},
        sort_keys=True, ensure_ascii=False,
    ).encode("utf-8")
    payload["signature"] = base64.b64encode(priv.sign(message)).decode()

    import core.utils.license_validator as lv

    monkeypatch.setattr(lv, "get_machine_fingerprint", lambda: "a" * 32)
    lic_path = tmp_path / "license_cache.json"
    lic_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    is_valid, reason, _ = validate_license_file(lic_path)
    assert not is_valid
    assert "未配置许可证公钥" in reason


# ---------------------------------------------------------------------------
# Fix 2（Attack 7）：license_state HMAC 签名与篡改 fail-closed
# ---------------------------------------------------------------------------


def test_state_signed_when_key_set(tmp_path, monkeypatch):
    """配置 STATE_KEY → 文件含 {data, sig} 且 sig 非空。"""
    monkeypatch.setenv(STATE_KEY_ENV, STATE_KEY)
    state_path = tmp_path / "license_state.json"
    sync_license_state(OLD_KEY, path=state_path)
    raw = json.loads(state_path.read_text(encoding="utf-8"))
    assert set(raw.keys()) == {"data", "sig"}
    assert raw["sig"]
    assert raw["data"]["active_license_key"] == OLD_KEY


def test_state_tamper_detected_fail_closed(tmp_path, monkeypatch):
    """篡改 state 内容 → check_sync_allowed 拒绝（fail-closed）。"""
    monkeypatch.setenv(STATE_KEY_ENV, STATE_KEY)
    state_path = tmp_path / "license_state.json"
    supersede(OLD_KEY, NEW_KEY, path=state_path)

    raw = json.loads(state_path.read_text(encoding="utf-8"))
    raw["data"]["grace_ends_at"] = (
        datetime.now(timezone.utc) + timedelta(days=30)
    ).isoformat()
    state_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    allowed, reason = check_sync_allowed(OLD_KEY, path=state_path)
    assert allowed is False
    assert "校验失败" in reason and "篡改" in reason


def test_state_tamper_blocks_sync_overwrite(tmp_path, monkeypatch, caplog):
    """篡改后 sync 不覆盖（避免攻击者诱导写回），拦截层保持拒绝。"""
    monkeypatch.setenv(STATE_KEY_ENV, STATE_KEY)
    state_path = tmp_path / "license_state.json"
    supersede(OLD_KEY, NEW_KEY, path=state_path)
    state_path.write_text("{tampered", encoding="utf-8")

    state = sync_license_state(NEW_KEY, path=state_path)
    assert state["active_license_key"] is None  # 未写回
    allowed, _ = check_sync_allowed(OLD_KEY, path=state_path)
    assert allowed is False


def test_legacy_state_with_key_treated_tampered(tmp_path, monkeypatch):
    """旧格式（无签名）state + 配置密钥 → 视为篡改，拒绝放行。"""
    monkeypatch.setenv(STATE_KEY_ENV, STATE_KEY)
    state_path = tmp_path / "license_state.json"
    state_path.write_text(
        json.dumps({"active_license_key": OLD_KEY, "superseded_by": NEW_KEY}),
        encoding="utf-8",
    )
    allowed, reason = check_sync_allowed(OLD_KEY, path=state_path)
    assert allowed is False
    assert "校验失败" in reason


def test_state_unsigned_mode_without_key(tmp_path, monkeypatch, caplog):
    """未配置密钥 → 无保护模式（sig 空），放行但告警。"""
    monkeypatch.delenv(STATE_KEY_ENV, raising=False)
    state_path = tmp_path / "license_state.json"
    supersede(OLD_KEY, NEW_KEY, path=state_path)
    raw = json.loads(state_path.read_text(encoding="utf-8"))
    assert raw["sig"] == ""
    allowed, _ = check_sync_allowed(OLD_KEY, path=state_path)
    assert allowed is True  # 宽限内


def test_sync_allowed_with_client_key_header(tmp_path, monkeypatch):
    """请求方携带 X-DDW-License-Key（旧码）→ 主系统权威判定拒绝（删本机文件无效）。"""
    monkeypatch.setenv(STATE_KEY_ENV, STATE_KEY)
    state_path = tmp_path / "license_state.json"
    state = supersede(OLD_KEY, NEW_KEY, path=state_path)
    state["grace_ends_at"] = (
        datetime.now(timezone.utc) - timedelta(days=1)
    ).isoformat()
    state_path.write_text(
        json.dumps({"data": state, "sig": ""}, ensure_ascii=False),
        encoding="utf-8",
    )
    # 用正确密钥重签
    from core.utils.license_state import _sign_state

    state_path.write_text(
        json.dumps({"data": state, "sig": _sign_state(state)}, ensure_ascii=False),
        encoding="utf-8",
    )

    # 即使本机无 license 文件（cache 不存在），携带 header 旧码也被拒
    allowed, reason = check_sync_allowed(OLD_KEY, path=state_path)
    assert allowed is False
    assert reason == "授权已更新，请联系经销商获取新授权码"


# ---------------------------------------------------------------------------
# Fix 2（Attack 8）：签名模式并发写原子性
# ---------------------------------------------------------------------------


def test_concurrent_writes_atomic_with_signature(tmp_path, monkeypatch):
    """签名模式并发写 → 文件始终为合法 {data, sig} 且签名可验证。"""
    monkeypatch.setenv(STATE_KEY_ENV, STATE_KEY)
    state_path = tmp_path / "license_state.json"
    errors: list = []

    def writer(key: str):
        try:
            for _ in range(15):
                sync_license_state(key, path=state_path)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [
        threading.Thread(target=writer, args=(OLD_KEY,)),
        threading.Thread(target=writer, args=(NEW_KEY,)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    raw = json.loads(state_path.read_text(encoding="utf-8"))
    assert set(raw.keys()) == {"data", "sig"}
    from core.utils.license_state import _verify_signature

    assert _verify_signature(raw["data"], raw["sig"], STATE_KEY)


# ---------------------------------------------------------------------------
# Fix 3（Attack 2）：Docker 指纹宿主 machine-id + 容器 id
# ---------------------------------------------------------------------------


def test_docker_container_id_parsing():
    """cgroup v1/v2 容器 ID 解析。"""
    from core.utils.machine_fingerprint import _docker_container_id_from_text

    v1 = (
        "12:pids:/docker/0123456789abcdef0123456789abcdef"
        "0123456789abcdef0123456789abcdef"
    )
    v2 = (
        "0::/system.slice/docker-abcdef0123456789abcdef0123456789abcdef"
        "0123456789abcdef0123456789abcdef.scope"
    )
    assert _docker_container_id_from_text(v1) == "0123456789abcdef" * 4
    assert _docker_container_id_from_text(v2) == "abcdef0123456789" * 4
    assert _docker_container_id_from_text("0::/") is None


def test_docker_primary_with_host_machine_id(tmp_path, monkeypatch):
    """宿主 machine-id 挂载 + 容器 id → 指纹主源组合。"""
    import core.utils.machine_fingerprint as mf

    monkeypatch.setattr(mf, "_is_docker", lambda: True)
    monkeypatch.setattr(mf, "_read_first_existing", lambda paths: "host-machine-id-123")
    monkeypatch.setattr(mf, "_docker_container_id", lambda: "c" * 64)
    assert mf._docker_primary_source() == (
        "docker:host=host-machine-id-123:container=" + "c" * 64
    )


def test_docker_primary_without_host_machine_id(tmp_path, monkeypatch, caplog):
    """宿主 machine-id 未挂载 → 降级 + 告警（跨机克隆检测降级）。"""
    import core.utils.machine_fingerprint as mf

    monkeypatch.setattr(mf, "_is_docker", lambda: True)
    monkeypatch.setattr(mf, "_read_first_existing", lambda paths: None)
    monkeypatch.setattr(mf, "_docker_container_id", lambda: "d" * 64)
    assert mf._docker_primary_source() == (
        "docker:container=" + "d" * 64 + ":host=unknown"
    )


# ---------------------------------------------------------------------------
# Fix 2 端到端：主系统权威判定（删本机 state 文件无法绕过）
# ---------------------------------------------------------------------------


def _point_paths(tmp_path, monkeypatch) -> tuple:
    """让 license 模块的 cache/state 路径指向 tmp（主系统视角）。"""
    from core.config import Settings

    lic_path = tmp_path / "license_cache.json"
    monkeypatch.setattr(
        "core.config._settings",
        Settings(raw={"license": {"cache_path": str(lic_path)}}),
    )
    return lic_path, tmp_path / "license_state.json"


def _build_kh_app(tmp_path, monkeypatch):
    """挂载知识库 router 的 mini app（主系统）；state 指向 tmp。"""
    from fastapi import FastAPI
    from httpx import ASGITransport

    _point_paths(tmp_path, monkeypatch)
    from plugins.ddw_knowledge_hierarchy.router import router as kh_router

    app = FastAPI()
    app.include_router(kh_router, prefix="/api/v1/plugins/ddw-knowledge-hierarchy")
    return ASGITransport(app=app)


async def test_upload_blocked_by_authority_state_even_if_local_file_deleted(
    tmp_path, monkeypatch
):
    """克隆容器删掉本机 license_cache/state 也没用：
    携带 X-DDW-License-Key=旧码 同步 → 主系统 state 判定超时 → 403。"""
    from datetime import datetime, timedelta, timezone

    from httpx import AsyncClient

    monkeypatch.setenv(STATE_KEY_ENV, STATE_KEY)
    transport = _build_kh_app(tmp_path, monkeypatch)

    # 主系统 state：旧码已被替换且超 7 天（注意：本机 license_cache 故意不存在
    # —— 模拟克隆容器删文件，判定只看请求方 header 的 key）
    state_path = tmp_path / "license_state.json"
    state = supersede(OLD_KEY, NEW_KEY, path=state_path)
    state["grace_ends_at"] = (
        datetime.now(timezone.utc) - timedelta(days=1)
    ).isoformat()
    from core.utils.license_state import _sign_state

    state_path.write_text(
        json.dumps({"data": state, "sig": _sign_state(state)}, ensure_ascii=False),
        encoding="utf-8",
    )
    assert not (tmp_path / "license_cache.json").exists()  # 本机 license 文件已删

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/plugins/ddw-knowledge-hierarchy/documents/upload",
            headers={"X-DDW-License-Key": OLD_KEY},
            files={"file": ("note.md", b"# cloned data\ncontent", "text/markdown")},
        )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "授权已更新，请联系经销商获取新授权码"


# ---------------------------------------------------------------------------
# 同步拦截全覆盖：新接入点集成测试（memory / skills / esg）
# ---------------------------------------------------------------------------


def _expired_supersede_state(tmp_path, monkeypatch) -> None:
    """主系统 state：旧码被替换且超 7 天（含正确 HMAC 签名）。"""
    from datetime import datetime, timedelta, timezone

    from core.utils.license_state import _sign_state

    monkeypatch.setenv(STATE_KEY_ENV, STATE_KEY)
    state_path = tmp_path / "license_state.json"
    state = supersede(OLD_KEY, NEW_KEY, path=state_path)
    state["grace_ends_at"] = (
        datetime.now(timezone.utc) - timedelta(days=1)
    ).isoformat()
    state_path.write_text(
        json.dumps({"data": state, "sig": _sign_state(state)}, ensure_ascii=False),
        encoding="utf-8",
    )


async def test_memory_create_blocked_when_superseded(tmp_path, monkeypatch):
    """ddw_memory POST /memories 接入拦截：旧码超期 + 请求方 header → 403。"""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    _point_paths(tmp_path, monkeypatch)
    _expired_supersede_state(tmp_path, monkeypatch)
    from plugins.ddw_memory.router import build_router

    app = FastAPI()
    app.include_router(build_router())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/plugins/ddw-memory/memories",
            headers={"X-DDW-License-Key": OLD_KEY},
            json={
                "layer": "department", "content": "x", "creator_id": 1, "tenant_id": 1
            },
        )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "授权已更新，请联系经销商获取新授权码"


async def test_skills_create_blocked_when_superseded(tmp_path, monkeypatch):
    """数字员工 skills POST /skills 接入拦截：旧码超期 → 403。"""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    _point_paths(tmp_path, monkeypatch)
    _expired_supersede_state(tmp_path, monkeypatch)
    from core.api.skills import router as skills_router

    from core.auth.jwt import create_access_token

    app = FastAPI()
    app.include_router(skills_router)
    transport = ASGITransport(app=app)
    token = create_access_token(user_id=1, tenant_id=1, role="member")
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/skills",
            headers={
                "Authorization": f"Bearer {token}",
                "X-DDW-License-Key": OLD_KEY,
            },
            json={"name": "t", "trigger": "t", "prompt": "t", "content": "t"},
        )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "授权已更新，请联系经销商获取新授权码"


async def test_esg_knowledge_batch_import_blocked(tmp_path, monkeypatch):
    """ddw_esg_knowledge POST /import/batch 接入拦截（sync 端点）：旧码超期 → 403。"""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    _point_paths(tmp_path, monkeypatch)
    _expired_supersede_state(tmp_path, monkeypatch)
    from plugins.ddw_esg_knowledge.routes import router as esg_kb_router

    app = FastAPI()
    app.include_router(esg_kb_router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/plugins/ddw-esg-knowledge/import/batch",
            headers={"X-DDW-License-Key": OLD_KEY},
            json={"file_paths": ["/tmp/x.md"]},
        )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "授权已更新，请联系经销商获取新授权码"


def test_locked_plugin_not_loaded(tmp_path, monkeypatch, caplog):
    """status: locked 插件仅入库不部署：load_plugins 跳过并日志注明。"""
    from core.config import Settings
    from core.main import load_plugins

    _make_plugin(tmp_path, "locked_plugin", "commercial")
    locked_manifest = tmp_path / "plugins" / "locked_plugin" / "manifest.yaml"
    locked_manifest.write_text(
        "name: locked_plugin\nlicense: commercial\nstatus: locked\nversion: 1.0.0\n",
        encoding="utf-8",
    )
    (tmp_path / "plugins" / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(
        "core.main.get_settings",
        lambda: Settings(
            raw={
                "plugins": {"root_dir": str(tmp_path / "plugins")},
                "license": {"cache_path": str(tmp_path / "license_cache.json")},
            }
        ),
    )
    monkeypatch.setenv("DDW_ENV", "production")

    import logging

    from fastapi import FastAPI

    with caplog.at_level(logging.WARNING, logger="core.main"):
        loaded = load_plugins(FastAPI())
    assert "locked_plugin" not in loaded
    assert any("locked" in r.message for r in caplog.records)
