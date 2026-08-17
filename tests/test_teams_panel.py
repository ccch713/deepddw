"""R4-8（DSH for Teams）：DSH 设置面板集成——插件包结构合法性测试。

验收：cordis.patch.yml 注册模式正确（settings.section 由客户端实现）；
package.json dsh 段完整；客户端组件存在；UI 只用 DSH CSS 变量（无自设色号）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest  # noqa: E402

PLUGIN_DIR = Path("plugins/dsh-teams-panel")


def test_cordis_patch_registration():
    """cordis.patch.yml 存在且含 insert 注册（与皮肤中心同级模式）。"""
    patch = PLUGIN_DIR / "cordis.patch.yml"
    assert patch.exists()
    content = patch.read_text(encoding="utf-8")
    assert "- insert:" in content
    assert "ddw-teams-panel" in content
    assert "@deepddw/dsh-teams-panel" in content


def test_package_json_dsh_field():
    """package.json 含 dsh.bundle.patch + dsh.client.inject。"""
    pkg = json.loads((PLUGIN_DIR / "package.json").read_text(encoding="utf-8"))
    assert pkg["dsh"]["bundle"]["patch"] == "./cordis.patch.yml"
    assert "inject" in pkg["dsh"]["client"]
    assert pkg["name"] == "@deepddw/dsh-teams-panel"
    assert pkg["version"] == "0.4.0"


def test_client_component_exists_and_uses_dsh_css():
    """客户端组件存在；UI 使用 DSH CSS 变量（无自设十六进制色号，主色除外）。"""
    client = PLUGIN_DIR / "src" / "client" / "index.ts"
    assert client.exists()
    content = client.read_text(encoding="utf-8")
    # settings.section slot 注册（与 dshmarket 同模式）
    assert "settings.section" in content
    assert "ctx.slots.inject" in content
    # 页签：记忆体/知识库/网络/用户/设备/文件库
    for tab in ("记忆体", "知识库", "网络", "用户", "设备", "文件库"):
        assert tab in content
    # 使用 DSH CSS 变量（--k-color-* / var(--k-...)
    assert "var(--k-color" in content
    # solo 模式隐藏「用户」页签
    assert "soloMode" in content and "soloHidden" in content
    # 禁止自设色号：十六进制仅允许作为 CSS 变量回退值（var(--k-*, #xxx)）
    import re

    hardcoded = []
    for l in content.splitlines():
        # 去掉 var(--k-*, fallback) 模式后仍含 # 才算自设
        stripped = re.sub(r"var\(--k-[\w-]+\s*,\s*#[0-9a-fA-F]{3,8}\)", "", l)
        if "#" in stripped:
            hardcoded.append(l)
    assert not hardcoded, f"存在自设色号: {hardcoded}"


def test_server_entry_exists():
    """服务端入口存在。"""
    assert (PLUGIN_DIR / "src" / "index.ts").exists()


def test_tsconfig_present():
    """tsconfig 存在（构建配置）。"""
    assert (PLUGIN_DIR / "tsconfig.json").exists()
    assert (PLUGIN_DIR / "tsconfig.client.json").exists()
