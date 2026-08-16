"""P1-2（multidevice）：可选 TLS 配置测试。

验收：security.tls.* 配置可解析；默认关闭（fail-closed）；env 可覆盖；
证书缺失时 enabled=true 不静默崩溃（entry_win 由人工验证，这里验证配置层）。
"""

from __future__ import annotations

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_tls_env(monkeypatch):
    """清除 TLS 相关 env（防测试污染）。"""
    for k in ("DDW_TLS_ENABLED", "DDW_TLS_CERT", "DDW_TLS_KEY", "DDW_TLS_PORT"):
        monkeypatch.delenv(k, raising=False)
    yield


def test_tls_disabled_by_default():
    """默认：TLS 关闭（fail-closed，不影响现有 HTTP）。"""
    from core.config import get_tls_config

    cfg = get_tls_config()
    assert cfg["enabled"] is False
    assert cfg["cert_file"] == ""
    assert cfg["key_file"] == ""


def test_tls_env_override(monkeypatch):
    """env 覆盖：DDW_TLS_ENABLED=true + 证书路径。"""
    from core.config import get_tls_config

    monkeypatch.setenv("DDW_TLS_ENABLED", "true")
    monkeypatch.setenv("DDW_TLS_CERT", "/tmp/cert.pem")
    monkeypatch.setenv("DDW_TLS_KEY", "/tmp/key.pem")
    monkeypatch.setenv("DDW_TLS_PORT", "9443")
    cfg = get_tls_config()
    assert cfg["enabled"] is True
    assert cfg["cert_file"] == "/tmp/cert.pem"
    assert cfg["key_file"] == "/tmp/key.pem"
    assert cfg["port"] == 9443


def test_tls_disabled_env_false(monkeypatch):
    """显式 DDW_TLS_ENABLED=false → 关闭。"""
    from core.config import get_tls_config

    monkeypatch.setenv("DDW_TLS_ENABLED", "false")
    monkeypatch.setenv("DDW_TLS_CERT", "/tmp/cert.pem")
    cfg = get_tls_config()
    assert cfg["enabled"] is False


def test_cert_script_exists_and_executable():
    """自签证书脚本存在且可执行（openssl 生成 1 年证书）。"""
    from pathlib import Path

    script = Path("scripts/gen_self_signed_cert.sh")
    assert script.exists()
    assert script.stat().st_mode & 0o111  # 可执行
    content = script.read_text(encoding="utf-8")
    assert "-days 365" in content  # 一年有效
    assert "subjectAltName" in content  # SAN 含 localhost/127.0.0.1
