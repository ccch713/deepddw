"""R4-7（DSH for Teams）：品牌可定制架构测试。

验收：get_branding 读取配置/env；launcher CSS 变量默认跟随 DSH；
branding 非空时覆盖（DOM 属性）；/api/v1/branding 端点公开可用。
"""

from __future__ import annotations

import os

os.environ.setdefault("DDW_ACCESS_TOKEN", "test-branding-token")

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("DDW_BRANDING_LOGO", "DDW_BRANDING_PRIMARY_COLOR",
              "DDW_BRANDING_WELCOME_TEXT"):
        monkeypatch.delenv(k, raising=False)
    yield


def test_branding_default_empty():
    """默认：全部为空（跟随 DSH 风格）。"""
    from core.config import get_branding

    b = get_branding()
    assert b["logo_url"] == "" and b["primary_color"] == ""
    assert b["welcome_text"] == "" and b["boot_animation"] == ""


def test_branding_env_override(monkeypatch):
    """env 覆盖：DDW_BRANDING_PRIMARY_COLOR 等。"""
    from core.config import get_branding

    monkeypatch.setenv("DDW_BRANDING_PRIMARY_COLOR", "#ff6600")
    monkeypatch.setenv("DDW_BRANDING_WELCOME_TEXT", "企业版启动")
    b = get_branding()
    assert b["primary_color"] == "#ff6600"
    assert b["welcome_text"] == "企业版启动"


def test_branding_config_yaml(monkeypatch, tmp_path):
    """deployment.yaml branding 段读取（mock settings.raw）。"""
    import core.config as cfg

    class FakeSettings:
        raw = {
            "branding": {
                "logo_url": "https://example.com/logo.png",
                "primary_color": "#123456",
            }
        }
        deployment_yaml_path = None

    orig = cfg.get_settings
    cfg.get_settings = lambda: FakeSettings()
    try:
        b = cfg.get_branding()
        assert b["logo_url"] == "https://example.com/logo.png"
        assert b["primary_color"] == "#123456"
        assert b["welcome_text"] == ""  # 未配置保持空
    finally:
        cfg.get_settings = orig


async def test_branding_endpoint_public(client):
    """/api/v1/branding 公开可访问（无需 Token——启动页首屏）。"""
    resp = await client.get("/api/v1/branding")
    assert resp.status_code == 200
    data = resp.json()
    for k in ("logo_url", "primary_color", "welcome_text", "boot_animation"):
        assert k in data


def test_launcher_css_variables_present():
    """launcher CSS 变量默认值跟随 DSH 风格（--ddw-* 定义）。"""
    html = open("frontend/deepddw-launcher.html", encoding="utf-8").read()
    assert "--ddw-primary-color" in html
    assert "--ddw-bg-color" in html
    assert "--ddw-font-family" in html
    # 默认值跟随 DSH 主色（00e5ff——非自设蓝色主题）
    assert "--ddw-primary-color:#00e5ff" in html
    # JS 拉取 branding 覆盖逻辑存在
    assert "applyBranding" in html and "api/v1/branding" in html
