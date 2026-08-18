"""v0.5.0 架构重写测试——cordis 插件结构 + 接口验证 + CSS 合规。

验收：cordis.patch.yml 注册正确；package.json dsh 段合法；
客户端组件存在且使用 DSH CSS 变量；无自定义色号；
onboarding slot 注入（settings.onboarding）；section slot 注入（settings.section）；
device/identify 端点存在。
"""

from __future__ import annotations

import json
from pathlib import Path

PLUGIN = Path("plugins/ddw-teams-panel")


def test_cordis_patch():
    content = (PLUGIN / "cordis.patch.yml").read_text(encoding="utf-8")
    assert "- insert:" in content
    assert "ddw-multiuser" in content


def test_package_json():
    pkg = json.loads((PLUGIN / "package.json").read_text(encoding="utf-8"))
    assert pkg["dsh"]["bundle"]["patch"] == "./cordis.patch.yml"
    assert pkg["version"] == "0.5.0"


def test_client_slots():
    content = (PLUGIN / "src" / "client" / "index.ts").read_text(encoding="utf-8")
    assert "settings.section" in content
    assert "settings.onboarding" in content
    assert "ctx.slots.inject" in content


def test_client_css_pure_dsh():
    content = (PLUGIN / "src" / "client" / "index.ts").read_text(encoding="utf-8")
    # 只允许 var(--k-color-*) 和 var(--k-color-primary,#00e5ff) 回退
    import re
    hardcoded = []
    for line in content.splitlines():
        stripped = re.sub(r"var\(--k-[\w-]+\s*,\s*#[0-9a-fA-F]{3,8}\)", "", line)
        if "#" in stripped and "--brand" not in stripped:
            hardcoded.append(line.strip())
    assert not hardcoded, f"自定义色号: {hardcoded[:3]}"


def test_m2_onboarding_slot_exists():
    content = (PLUGIN / "src" / "client" / "index.ts").read_text(encoding="utf-8")
    assert "settings.onboarding" in content
    assert "deepddw_onboarded" in content


def test_m3_settings_modes():
    content = (PLUGIN / "src" / "client" / "index.ts").read_text(encoding="utf-8")
    assert "一人多设备" in content and "家庭多人" in content and "小团队协作" in content


def test_m4_identify_slot():
    content = (PLUGIN / "src" / "client" / "index.ts").read_text(encoding="utf-8")
    assert "deepddw_member_id" in content
    assert "你是谁" in content
    assert "member_id" in content


def test_m5_member_management():
    content = (PLUGIN / "src" / "client" / "index.ts").read_text(encoding="utf-8")
    assert "member/add" in content
    assert "member/revoke" in content


def test_m6_upgrade_entry():
    content = (PLUGIN / "src" / "client" / "index.ts").read_text(encoding="utf-8")
    assert "/api/v1/version" in content
    assert "deepDDW" in content


def test_client_bundle_exists():
    """lib/client.js 存在且符合 __ModuleLoader__ 格式（DSH 加载所需）。"""
    assert (PLUGIN / "lib" / "client.js").exists()
    content = (PLUGIN / "lib" / "client.js").read_text(encoding="utf-8")
    assert "window.__ModuleLoader__.load" in content
    assert "factory:" in content
    assert "@deepddw/ddw-teams-panel" in content


def test_server_entry():
    assert (PLUGIN / "src" / "index.js").exists()


def test_device_identify_endpoint():
    """M4：POST /api/v1/device/identify 端点存在。"""
    import core.api.teams as t

    assert hasattr(t, "device_identify") or "device_identify" in dir(t)
