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
    assert pkg["version"] == "0.7.0"


def test_v06_left_rail_pairing():
    """v0.7.0 左栏入口：panellist 与 main 必须成对注册且 id 与 key 同值。

    契约依据（DSH 0.2.2-rc.5 类型定义）：
    - sidebar.panellist（list/root，声明于 dsh-client-ui-sidebar）
    - main（keyed/root，声明于 dsh-client-ui-layout）
    只注册图标不注册 main = 死按钮；只注册 main = 没人点得到。
    """
    src = (PLUGIN / "src" / "client" / "index.ts").read_text(encoding="utf-8")
    assert "sidebar.panellist" in src
    assert "'main'" in src
    assert "PANEL_ID = 'ddw-teams'" in src
    # 注册守卫：必须经 slots.inject 等槽声明（直接注册会 slot not declared → fiber failed）
    assert "registerWhenDeclared" in src
    assert "ctx.slots.inject(slot" in src
    # package.json：inject 白名单必须含声明这两个槽的包
    pkg = json.loads((PLUGIN / "package.json").read_text(encoding="utf-8"))
    inject = pkg["dsh"]["client"]["inject"]
    assert "@deepseek-ai/dsh-client-ui-sidebar" in inject
    assert "@deepseek-ai/dsh-client-ui-layout" in inject


def test_v06_left_rail_naming():
    """v0.7.0 命名裁定：左栏/设置页 = 团队管理（Team Admin），右栏页签 = 团队（Team）。"""
    src = (PLUGIN / "src" / "client" / "index.ts").read_text(encoding="utf-8")
    assert "团队管理" in src
    assert "Team Admin" in src


def test_v06_right_pane_tab():
    """v0.7.0 右栏页签（裁定方案 C）：sidebarRightTabs 服务 + sidebar.right.pane.tab keyed 槽。"""
    src = (PLUGIN / "src" / "client" / "index.ts").read_text(encoding="utf-8")
    assert "sidebar.right.pane.tab" in src
    assert "ddw-team-tab" in src
    assert "sidebarRightTabs" in src
    assert "'团队'" in src
    pkg = json.loads((PLUGIN / "package.json").read_text(encoding="utf-8"))
    assert "@deepseek-ai/dsh-client-ui-sidebar-right" in pkg["dsh"]["client"]["inject"]


def test_v06_role_anti_spoof_client():
    """v0.7.0 客户端配合角色层：X-DDW-Device 头 + 绑定码输入 + 403 提示。"""
    src = (PLUGIN / "src" / "client" / "index.ts").read_text(encoding="utf-8")
    assert "X-DDW-Device" in src
    assert "invite_code" in src
    assert "绑定码" in src
    assert "403" in src


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
    # 允许语义色号（错误红、成功绿、离线灰——状态指示色，非主题色）
    SEMANTIC = {"#e74c3c", "#2ecc71", "#888", "#888888", "#e74c3c"}
    for line in content.splitlines():
        stripped = re.sub(r"var\(--k-[\w-]+\s*,\s*#[0-9a-fA-F]{3,8}\)", "", line)
        if "#" in stripped and "--brand" not in stripped and not any(c in stripped for c in SEMANTIC):
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
    assert "请输入你的身份" in content
    assert "member_id" in content


def test_m5_member_management():
    content = (PLUGIN / "src" / "client" / "index.ts").read_text(encoding="utf-8")
    assert "member/add" in content
    assert "member/revoke" in content


def test_m6_upgrade_entry():
    content = (PLUGIN / "src" / "client" / "index.ts").read_text(encoding="utf-8")
    assert "/api/v1/device/identify" in content
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
