"""P0 许可证安全升级测试（Ed25519 / fail-closed / 机器指纹绑定）。

覆盖：
1. Ed25519 验签通过
2. 篡改任意字段（valid_to）→ 验证失败
3. 旧 HMAC 格式 → "许可证格式过旧，请联系锐果换发"
4. 机器指纹不匹配 → "许可证与当前机器不匹配，如需迁移请联系锐果"
5. 过期 / 损坏 / 缺失 / 缺签名 / 缺指纹
6. 生产模式 fail-closed（无效/缺失 license → 只加载 free 插件，
   commercial 注明 not licensed）
7. 非生产模式无 license → 全量加载 + "no license in dev mode" 警告
8. 有效许可证 → 授权商业插件正常加载
9. scripts 发证脚本端到端（gen → issue → validate 互通）
10. 机器指纹模块组合稳定性
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from core.utils.license_validator import validate_license_file

REPO_ROOT = Path(__file__).resolve().parent.parent
VALID_MACHINE_FP = "a" * 32


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


# ---------------------------------------------------------------------------
# 测试工具：生成 Ed25519 密钥对 + 签发 license（与 scripts/issue_license.py 同规范）
# ---------------------------------------------------------------------------


def _make_keypair() -> tuple:
    """返回 (Ed25519PrivateKey, base64 公钥)。"""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv = Ed25519PrivateKey.generate()
    pub_b64 = base64.b64encode(priv.public_key().public_bytes_raw()).decode()
    return priv, pub_b64


def _sign_payload(priv, payload: dict) -> str:
    """按客户端同款规范化消息签名，返回 base64 签名。"""
    sign_data = {k: v for k, v in payload.items() if k != "signature"}
    message = json.dumps(sign_data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return base64.b64encode(priv.sign(message)).decode()


def _write_license(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "license_cache.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _build_license(
    priv,
    *,
    valid_to: str = "",
    machine_fp: str = VALID_MACHINE_FP,
    extra: dict | None = None,
) -> dict:
    today = date.today()
    payload = {
        "license_key": "LIC-TEST-001",
        "customer": "测试客户",
        "instance_id": "test-instance",
        "machine_fingerprint": machine_fp,
        "valid_from": today.isoformat(),
        "valid_to": valid_to or (today + timedelta(days=365)).isoformat(),
        "authorized_plugins": ["ddw-license-core"],
        "issued_by": "DDW-Admin",
        "issued_at": today.isoformat(),
        "license_format_version": 2,
        "sig_algo": "ed25519",
    }
    if extra:
        payload.update(extra)
    payload["signature"] = _sign_payload(priv, payload)
    return payload


@pytest.fixture(autouse=True)
def _monkeypatch_fingerprint(monkeypatch):
    """默认让本机指纹等于测试值（许可证绑定值），各测试再按需覆盖。"""
    import core.utils.license_validator as lv

    monkeypatch.setattr(lv, "get_machine_fingerprint", lambda: VALID_MACHINE_FP)


# ---------------------------------------------------------------------------
# 1. Ed25519 验签
# ---------------------------------------------------------------------------


def test_valid_ed25519_license_passes(tmp_path, _monkeypatch_fingerprint):
    priv, pub_b64 = _make_keypair()
    lic_path = _write_license(tmp_path, _build_license(priv))
    is_valid, reason, data = validate_license_file(lic_path, public_key=pub_b64)
    assert is_valid, reason
    assert reason == "许可证验证通过"
    assert data["sig_algo"] == "ed25519"


def test_signature_tampering_detected(tmp_path, _monkeypatch_fingerprint):
    priv, pub_b64 = _make_keypair()
    payload = _build_license(priv)
    # 篡改授权插件（签名不匹配）
    payload["authorized_plugins"] = ["ddw-bid-writer", "*"]
    lic_path = _write_license(tmp_path, payload)
    is_valid, reason, _ = validate_license_file(lic_path, public_key=pub_b64)
    assert not is_valid
    assert "签名验证失败" in reason


def test_tampered_valid_to_fails(tmp_path, _monkeypatch_fingerprint):
    priv, pub_b64 = _make_keypair()
    payload = _build_license(priv)
    payload["valid_to"] = (date.today() + timedelta(days=3650)).isoformat()  # 篡改延长
    lic_path = _write_license(tmp_path, payload)
    is_valid, reason, _ = validate_license_file(lic_path, public_key=pub_b64)
    assert not is_valid
    assert "签名验证失败" in reason


def test_wrong_public_key_rejected(tmp_path, _monkeypatch_fingerprint):
    priv, _ = _make_keypair()
    _, other_pub = _make_keypair()
    lic_path = _write_license(tmp_path, _build_license(priv))
    is_valid, reason, _ = validate_license_file(lic_path, public_key=other_pub)
    assert not is_valid
    assert "签名验证失败" in reason


def test_missing_signature_fails(tmp_path, _monkeypatch_fingerprint):
    priv, _ = _make_keypair()
    payload = _build_license(priv)
    del payload["signature"]
    lic_path = _write_license(tmp_path, payload)
    is_valid, reason, _ = validate_license_file(lic_path)
    assert not is_valid
    assert "缺少签名" in reason


# ---------------------------------------------------------------------------
# 2. 旧格式（HMAC）检测
# ---------------------------------------------------------------------------


def test_old_hmac_format_detected(tmp_path):
    """旧 HMAC 格式：64 位 hex 签名 + 无 sig_algo 标记 → 提示换发，不放行。"""
    today = date.today()
    payload = {
        "license_key": "LIC-OLD-001",
        "customer": "旧客户",
        "instance_id": "old-instance",
        "valid_from": today.isoformat(),
        "valid_to": (today + timedelta(days=365)).isoformat(),
        "authorized_plugins": ["*"],
        "signature": "ab12" * 16,  # 64 位 hex（旧 HMAC-SHA256 hexdigest 特征）
    }
    lic_path = _write_license(tmp_path, payload)
    is_valid, reason, _ = validate_license_file(
        lic_path, public_key=base64.b64encode(b"a" * 32).decode()
    )
    assert not is_valid
    assert reason == "许可证格式过旧，请联系锐果换发"


# ---------------------------------------------------------------------------
# 3. 机器指纹绑定
# ---------------------------------------------------------------------------


def test_machine_fingerprint_mismatch_fails(tmp_path, monkeypatch):
    import core.utils.license_validator as lv

    priv, pub_b64 = _make_keypair()
    lic_path = _write_license(tmp_path, _build_license(priv, machine_fp="b" * 32))
    monkeypatch.setattr(lv, "get_machine_fingerprint", lambda: "c" * 32)
    is_valid, reason, _ = validate_license_file(lic_path, public_key=pub_b64)
    assert not is_valid
    assert "许可证与当前机器不匹配，如需迁移请联系锐果" in reason


def test_missing_machine_fingerprint_fails(tmp_path, _monkeypatch_fingerprint):
    priv, pub_b64 = _make_keypair()
    payload = _build_license(priv)
    del payload["machine_fingerprint"]
    # 删字段后重签：签名有效，仅缺指纹
    payload["signature"] = _sign_payload(priv, payload)
    lic_path = _write_license(tmp_path, payload)
    is_valid, reason, _ = validate_license_file(lic_path, public_key=pub_b64)
    assert not is_valid
    assert "缺少机器指纹" in reason


# ---------------------------------------------------------------------------
# 4. 有效期 / 文件损坏 / 缺失
# ---------------------------------------------------------------------------


def test_expired_license_fails(tmp_path, _monkeypatch_fingerprint):
    priv, pub_b64 = _make_keypair()
    lic_path = _write_license(
        tmp_path,
        _build_license(priv, valid_to=(date.today() - timedelta(days=1)).isoformat()),
    )
    is_valid, reason, _ = validate_license_file(lic_path, public_key=pub_b64)
    assert not is_valid
    assert "已过期" in reason


def test_corrupt_license_file_fails(tmp_path):
    lic_path = tmp_path / "license_cache.json"
    lic_path.write_text("{ not valid json !!!", encoding="utf-8")
    is_valid, reason, _ = validate_license_file(lic_path)
    assert not is_valid
    assert "读取失败" in reason


def test_missing_license_file_fails(tmp_path):
    is_valid, reason, _ = validate_license_file(tmp_path / "no_such_file.json")
    assert not is_valid
    assert "不存在" in reason


def test_machine_fingerprint_shape_and_stability(monkeypatch):
    import core.utils.machine_fingerprint as mf

    monkeypatch.setattr(
        mf, "_get_primary_fingerprint_source", lambda: "machine-id-ABC123"
    )
    monkeypatch.setattr(mf, "get_hostname", lambda: "test-host")
    fp1 = mf.get_machine_fingerprint()
    fp2 = mf.get_machine_fingerprint()
    assert len(fp1) == 32
    assert fp1 == fp2  # 同一机器稳定
    expected = hashlib.sha256(b"machine-id-ABC123\ntest-host").hexdigest()[:32]
    assert fp1 == expected


# ---------------------------------------------------------------------------
# 5. load_plugins 环境门控（fail-closed / dev 全量）
# ---------------------------------------------------------------------------


def _make_fake_plugin(tmp_path: Path, name: str, tier: str) -> None:
    d = tmp_path / "plugins" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.yaml").write_text(
        f"name: {name}\nlicense: {tier}\nversion: 1.0.0\nconfig: {{}}\n",
        encoding="utf-8",
    )
    (d / "plugin.py").write_text(
        "class Plugin:\n"
        "    def __init__(self, app, config=None, manifest=None):\n"
        "        self.app = app\n"
        "        self.config = config or {}\n"
        "        self.manifest = manifest or {}\n",
        encoding="utf-8",
    )


def _setup_loader(tmp_path, monkeypatch, license_payload=None, raw_extra=None):
    """搭好 tmp 插件根 + 假 settings + sys.path，返回 settings 对象。"""
    from core.config import Settings
    from core.main import load_plugins

    _make_fake_plugin(tmp_path, "free_plugin", "free")
    _make_fake_plugin(tmp_path, "commercial_plugin", "commercial")
    (tmp_path / "plugins" / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))

    lic_path = tmp_path / "license_cache.json"
    if license_payload is not None:
        lic_path.write_text(
            json.dumps(license_payload, ensure_ascii=False), encoding="utf-8"
        )

    raw = {
        "plugins": {"root_dir": str(tmp_path / "plugins")},
        "license": {"cache_path": str(lic_path)},
    }
    if raw_extra:
        raw.update(raw_extra)
    settings = Settings(raw=raw)
    monkeypatch.setattr("core.main.get_settings", lambda: settings)
    return load_plugins, lic_path


def test_load_plugins_fail_closed_invalid_license(tmp_path, monkeypatch, caplog):
    """生产模式 + 无效 license → 只加载 free 插件，commercial 注明 not licensed。"""
    monkeypatch.setenv("DDW_ENV", "production")
    priv, _ = _make_keypair()
    payload = _build_license(priv)
    payload["valid_to"] = (
        date.today() + timedelta(days=9999)
    ).isoformat()  # 篡改 → 验签失败
    load_plugins, _ = _setup_loader(tmp_path, monkeypatch, license_payload=payload)

    from fastapi import FastAPI

    with caplog.at_level(logging.WARNING, logger="core.main"):
        loaded = load_plugins(FastAPI())
    assert "free_plugin" in loaded
    assert "commercial_plugin" not in loaded
    assert any("not licensed" in r.message for r in caplog.records)
    assert any("fail-closed" in r.message for r in caplog.records)


def test_load_plugins_fail_closed_no_license_file(tmp_path, monkeypatch, caplog):
    """生产模式 + 无 license 文件 → 只加载 free 插件。"""
    monkeypatch.setenv("DDW_ENV", "production")
    load_plugins, _ = _setup_loader(tmp_path, monkeypatch, license_payload=None)

    from fastapi import FastAPI

    with caplog.at_level(logging.WARNING, logger="core.main"):
        loaded = load_plugins(FastAPI())
    assert "free_plugin" in loaded
    assert "commercial_plugin" not in loaded
    assert any("no license file in production" in r.message for r in caplog.records)


def test_load_plugins_fail_closed_corrupt_license_file(tmp_path, monkeypatch, caplog):
    """生产模式 + license 文件损坏 → fail-closed，只加载 free 插件。"""
    monkeypatch.setenv("DDW_ENV", "production")
    load_plugins, _ = _setup_loader(
        tmp_path, monkeypatch, license_payload={"broken": "{ not valid json !!!"}
    )

    from fastapi import FastAPI

    with caplog.at_level(logging.WARNING, logger="core.main"):
        loaded = load_plugins(FastAPI())
    assert "free_plugin" in loaded
    assert "commercial_plugin" not in loaded
    assert any("fail-closed" in r.message for r in caplog.records)


def test_load_plugins_dev_mode_full_load(tmp_path, monkeypatch, caplog):
    """非生产模式 + 无 license 文件 → 全量加载 + no license in dev mode 警告。"""
    monkeypatch.delenv("DDW_ENV", raising=False)  # 默认 development
    load_plugins, _ = _setup_loader(tmp_path, monkeypatch, license_payload=None)

    from fastapi import FastAPI

    with caplog.at_level(logging.WARNING, logger="core.main"):
        loaded = load_plugins(FastAPI())
    assert "free_plugin" in loaded
    assert "commercial_plugin" in loaded  # dev 不锁死
    assert any("no license in dev mode" in r.message for r in caplog.records)


def test_load_plugins_valid_license_authorizes_commercial(
    tmp_path, monkeypatch, _monkeypatch_fingerprint
):
    """生产模式 + 有效 license（授权商业插件）→ free + 授权 commercial 都加载。"""
    monkeypatch.setenv("DDW_ENV", "production")
    priv, pub_b64 = _make_keypair()
    monkeypatch.setenv("DDW_LICENSE_PUBLIC_KEY", pub_b64)
    payload = _build_license(priv, extra={"authorized_plugins": ["commercial-plugin"]})
    load_plugins, _ = _setup_loader(tmp_path, monkeypatch, license_payload=payload)

    from fastapi import FastAPI

    loaded = load_plugins(FastAPI())
    assert "free_plugin" in loaded
    assert "commercial_plugin" in loaded


def test_load_plugins_unlicensed_commercial_skipped(tmp_path, monkeypatch, caplog):
    """生产模式 + 有效 license 但未授权该商业插件 → 跳过并提示 not licensed。"""
    monkeypatch.setenv("DDW_ENV", "production")
    priv, pub_b64 = _make_keypair()
    monkeypatch.setenv("DDW_LICENSE_PUBLIC_KEY", pub_b64)
    payload = _build_license(priv, extra={"authorized_plugins": ["ddw-license-core"]})
    load_plugins, _ = _setup_loader(tmp_path, monkeypatch, license_payload=payload)

    from fastapi import FastAPI

    with caplog.at_level(logging.WARNING, logger="core.main"):
        loaded = load_plugins(FastAPI())
    assert "free_plugin" in loaded
    assert "commercial_plugin" not in loaded
    assert any("not licensed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# 6. scripts 发证端端到端
# ---------------------------------------------------------------------------


def test_scripts_gen_issue_validate_roundtrip(tmp_path, monkeypatch):
    """gen_license_keys → issue_license → validate_license_file 互通，私钥权限 600。"""
    import core.utils.license_validator as lv

    scripts = REPO_ROOT / "scripts"
    keys = tmp_path / "keys"
    keys.mkdir()

    r1 = subprocess.run(
        [
            sys.executable,
            str(scripts / "gen_license_keys.py"),
            "--output-dir",
            str(keys),
        ],
        capture_output=True,
        text=True,
    )
    assert r1.returncode == 0, r1.stderr
    priv_pem = keys / "license_signing_private_key.pem"
    assert priv_pem.exists()
    assert oct(priv_pem.stat().st_mode & 0o777) == "0o600"
    pub_b64 = [
        ln.strip()
        for ln in r1.stdout.splitlines()
        if ln.strip().endswith("=") and len(ln.strip()) == 44
    ][-1]

    lic_path = tmp_path / "license_cache.json"
    r2 = subprocess.run(
        [
            sys.executable,
            str(scripts / "issue_license.py"),
            "--private-key", str(priv_pem),
            "--license-key", "LIC-SCRIPT-001",
            "--customer", "脚本测试客户",
            "--instance-id", "script-instance",
            "--machine-fingerprint", VALID_MACHINE_FP,
            "--valid-days", "30",
            "--authorized-plugins", "ddw-license-core,ddw-instance-binding",
            "--output", str(lic_path),
        ],
        capture_output=True,
        text=True,
    )
    assert r2.returncode == 0, r2.stderr

    monkeypatch.setattr(lv, "get_machine_fingerprint", lambda: VALID_MACHINE_FP)
    is_valid, reason, data = validate_license_file(lic_path, public_key=pub_b64)
    assert is_valid, reason
    assert data["license_format_version"] == 2
    assert data["sig_algo"] == "ed25519"
    assert len(base64.b64decode(data["signature"])) == 64
    assert data["authorized_plugins"] == ["ddw-license-core", "ddw-instance-binding"]

    # 客户端侧没有任何私钥文件（仅 tmp_path 中脚本产物）
    validator_src = (REPO_ROOT / "core" / "utils" / "license_validator.py").read_text(
        encoding="utf-8"
    )
    assert "PRIVATE KEY" not in validator_src
