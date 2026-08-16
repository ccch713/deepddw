"""LAN 免密模式专项测试（体验优化 A，2026-08-16）。

- 开启 DDW_LAN_BYPASS=1：本机/内网访问免 Token 放行；
- 默认关闭（P0-4）；
- 关闭（DDW_LAN_BYPASS=0，conftest 默认）：无 Token → 401（保持安全语义）；
- 外网 IP（模拟 X-Forwarded-For 公网地址）即使开启免密也要求 Token。

注：conftest.py 默认设 DDW_LAN_BYPASS=0，本文件各用例显式控制。
本文件只做函数级测试（token_gate 判定逻辑），不实例化完整 app——
避免与 test_mcp_streamable_http.py 的 FastMCP session manager 单例冲突
（create_app 会初始化全局 FastMCP，两文件共享单例导致生命周期互扰）。
"""

from __future__ import annotations


from core.security.token_gate import (
    _authorized,
    is_lan_client,
    lan_bypass_enabled,
    verify_token,
)

TOKEN = "lan-test-token"


def _reset_env(monkeypatch):
    monkeypatch.setenv("DDW_ACCESS_TOKEN", TOKEN)
    monkeypatch.delenv("DDW_LAN_BYPASS", raising=False)


def test_lan_bypass_enabled_default_false(monkeypatch):
    """未显式配置时 LAN 免密默认关闭（P0-4 安全优先；公网误部署不暴露）。"""
    _reset_env(monkeypatch)
    assert lan_bypass_enabled() is False


def test_lan_bypass_disabled_by_env(monkeypatch):
    _reset_env(monkeypatch)
    monkeypatch.setenv("DDW_LAN_BYPASS", "0")
    assert lan_bypass_enabled() is False


def test_is_lan_client_private_ranges():
    assert is_lan_client("192.168.1.7") is True
    assert is_lan_client("10.0.0.5") is True
    assert is_lan_client("172.16.3.9") is True
    assert is_lan_client("127.0.0.1") is True
    assert is_lan_client("8.145.35.164") is False
    assert is_lan_client("100.64.0.1") is False  # CGNAT 视为非内网（保守）
    assert is_lan_client(None) is False


def test_authorized_lan_bypass_no_token(monkeypatch):
    """免密开启 + 内网来源 → 无 Token 也放行（A 核心）。"""
    _reset_env(monkeypatch)
    monkeypatch.setenv("DDW_LAN_BYPASS", "1")
    assert _authorized(token=None, host="192.168.1.7") is True


def test_authorized_lan_bypass_rejects_external(monkeypatch):
    """免密开启 + 外网来源 → 无 Token 拒绝（外网仍要 Token）。"""
    _reset_env(monkeypatch)
    monkeypatch.setenv("DDW_LAN_BYPASS", "1")
    assert _authorized(token=None, host="8.145.35.164") is False


def test_authorized_external_with_valid_token(monkeypatch):
    """外网来源 + 正确 Token → 放行。"""
    _reset_env(monkeypatch)
    monkeypatch.setenv("DDW_LAN_BYPASS", "1")
    assert _authorized(token=TOKEN, host="8.145.35.164") is True


def test_authorized_bypass_disabled_requires_token(monkeypatch):
    """免密关闭 + 内网来源 + 无 Token → 拒绝（恢复原安全语义）。"""
    _reset_env(monkeypatch)
    monkeypatch.setenv("DDW_LAN_BYPASS", "0")
    assert _authorized(token=None, host="127.0.0.1") is False


def test_authorized_bypass_disabled_valid_token_ok(monkeypatch):
    """免密关闭 + 内网来源 + 正确 Token → 放行。"""
    _reset_env(monkeypatch)
    monkeypatch.setenv("DDW_LAN_BYPASS", "0")
    assert _authorized(token=TOKEN, host="127.0.0.1") is True


def test_verify_token_constant_time(monkeypatch):
    """verify_token 常量时间比较（短码/长码都支持，B 短码体验）。"""
    _reset_env(monkeypatch)
    assert verify_token(TOKEN) is True
    assert verify_token("ddw-7f3k") is False
    assert verify_token("") is False
