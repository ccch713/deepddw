"""插件注册表测试。

测试扫描、缓存、过滤等注册表核心功能。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.marketplace.plugin_market import PluginCategory
from core.marketplace.plugin_registry import PluginRegistry


@pytest.fixture
def temp_plugins_dir(tmp_path: Path) -> Path:
    """创建临时插件目录，包含测试插件。"""
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()

    # 插件 1: token-manager
    plugin1_dir = plugins_dir / "token-manager"
    plugin1_dir.mkdir()
    manifest1 = {
        "name": "token-manager",
        "version": "1.0.0",
        "description": "Token 额度管理插件",
        "author": "DDW Team",
        "license": "MIT",
        "engine": ">=0.1.0",
        "permissions": ["database", "config"],
        "ecosystem": {
            "category": "infrastructure",
            "tags": ["token", "quota"],
        },
    }
    (plugin1_dir / "manifest.yaml").write_text(
        yaml.dump(manifest1, allow_unicode=True), encoding="utf-8"
    )

    # 插件 2: data-exporter
    plugin2_dir = plugins_dir / "data-exporter"
    plugin2_dir.mkdir()
    manifest2 = {
        "name": "data-exporter",
        "version": "0.5.0",
        "description": "数据导出工具",
        "author": "Community",
        "license": "Apache-2.0",
        "ecosystem": {
            "category": "data_analytics",
            "tags": ["export", "csv"],
        },
    }
    (plugin2_dir / "manifest.yaml").write_text(
        yaml.dump(manifest2, allow_unicode=True), encoding="utf-8"
    )

    # 插件 3: ai-assistant
    plugin3_dir = plugins_dir / "ai-assistant"
    plugin3_dir.mkdir()
    manifest3 = {
        "name": "ai-assistant",
        "version": "2.1.0",
        "description": "AI 助手插件",
        "author": "AI Lab",
        "ecosystem": {
            "category": "ai_tools",
            "tags": ["chat", "assistant"],
        },
    }
    (plugin3_dir / "manifest.yaml").write_text(
        yaml.dump(manifest3, allow_unicode=True), encoding="utf-8"
    )

    # 无效插件（缺少 name）
    bad_dir = plugins_dir / "bad-plugin"
    bad_dir.mkdir()
    (bad_dir / "manifest.yaml").write_text(
        yaml.dump({"version": "1.0.0"}), encoding="utf-8"
    )

    # 没有 manifest 的目录
    no_manifest_dir = plugins_dir / "empty-plugin"
    no_manifest_dir.mkdir()

    return plugins_dir


class TestPluginRegistry:
    """插件注册表核心功能测试。"""

    def test_scan_local_plugins(self, temp_plugins_dir: Path) -> None:
        """测试扫描本地插件目录。"""
        registry = PluginRegistry(plugins_root=temp_plugins_dir)
        listings = registry.scan_local_plugins()

        # 应该发现 3 个有效插件（排除 bad-plugin 和 empty-plugin）
        assert len(listings) == 3
        names = {l.name for l in listings}
        assert "token-manager" in names
        assert "data-exporter" in names
        assert "ai-assistant" in names

    def test_scan_empty_directory(self, tmp_path: Path) -> None:
        """测试扫描空目录。"""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        registry = PluginRegistry(plugins_root=empty_dir)
        listings = registry.scan_local_plugins()
        assert listings == []

    def test_scan_nonexistent_directory(self, tmp_path: Path) -> None:
        """测试扫描不存在的目录。"""
        registry = PluginRegistry(plugins_root=tmp_path / "nonexistent")
        listings = registry.scan_local_plugins()
        assert listings == []

    def test_parse_manifest_fields(self, temp_plugins_dir: Path) -> None:
        """测试 manifest 字段解析完整性。"""
        registry = PluginRegistry(plugins_root=temp_plugins_dir)
        listings = registry.scan_local_plugins()

        token_mgr = next(l for l in listings if l.name == "token-manager")
        assert token_mgr.version == "1.0.0"
        assert token_mgr.description == "Token 额度管理插件"
        assert token_mgr.author == "DDW Team"
        assert token_mgr.license == "MIT"
        assert token_mgr.engine == ">=0.1.0"
        assert token_mgr.category == PluginCategory.INFRASTRUCTURE
        assert "database" in (token_mgr.permissions or [])
        assert "config" in (token_mgr.permissions or [])
        assert "token" in (token_mgr.tags or [])

    def test_get_plugin_detail(self, temp_plugins_dir: Path) -> None:
        """测试获取单个插件详情。"""
        registry = PluginRegistry(plugins_root=temp_plugins_dir)
        detail = registry.get_plugin_detail("token-manager")

        assert detail is not None
        assert detail.name == "token-manager"
        assert detail.version == "1.0.0"

    def test_get_plugin_detail_not_found(self, temp_plugins_dir: Path) -> None:
        """测试获取不存在的插件详情。"""
        registry = PluginRegistry(plugins_root=temp_plugins_dir)
        detail = registry.get_plugin_detail("nonexistent")
        assert detail is None

    def test_get_plugin_listings_with_category_filter(
        self, temp_plugins_dir: Path
    ) -> None:
        """测试按分类过滤插件列表。"""
        registry = PluginRegistry(plugins_root=temp_plugins_dir)

        infra_plugins = registry.get_plugin_listings(
            category=PluginCategory.INFRASTRUCTURE
        )
        assert len(infra_plugins) == 1
        assert infra_plugins[0].name == "token-manager"

        ai_plugins = registry.get_plugin_listings(category=PluginCategory.AI_TOOLS)
        assert len(ai_plugins) == 1
        assert ai_plugins[0].name == "ai-assistant"

    def test_get_plugin_listings_with_search(self, temp_plugins_dir: Path) -> None:
        """测试关键词搜索。"""
        registry = PluginRegistry(plugins_root=temp_plugins_dir)

        results = registry.get_plugin_listings(search="token")
        assert len(results) == 1
        assert results[0].name == "token-manager"

        results = registry.get_plugin_listings(search="data")
        assert len(results) == 1
        assert results[0].name == "data-exporter"

    def test_get_plugin_listings_search_no_match(
        self, temp_plugins_dir: Path
    ) -> None:
        """测试搜索无匹配结果。"""
        registry = PluginRegistry(plugins_root=temp_plugins_dir)
        results = registry.get_plugin_listings(search="nonexistent")
        assert results == []

    def test_refresh_registry(self, temp_plugins_dir: Path) -> None:
        """测试刷新注册表缓存。"""
        registry = PluginRegistry(plugins_root=temp_plugins_dir)

        # 首次扫描
        listings1 = registry.scan_local_plugins()
        assert len(listings1) == 3

        # 强制刷新
        listings2 = registry.refresh_registry()
        assert len(listings2) == 3

    def test_cache_invalidation(self, temp_plugins_dir: Path) -> None:
        """测试缓存在 TTL 后失效。"""
        registry = PluginRegistry(plugins_root=temp_plugins_dir)

        # 首次扫描，填充缓存
        registry.scan_local_plugins()

        # 添加新插件
        new_plugin_dir = temp_plugins_dir / "new-plugin"
        new_plugin_dir.mkdir()
        manifest = {
            "name": "new-plugin",
            "version": "1.0.0",
            "description": "新插件",
        }
        (new_plugin_dir / "manifest.yaml").write_text(
            yaml.dump(manifest), encoding="utf-8"
        )

        # 强制刷新后应该能发现新插件
        listings = registry.refresh_registry()
        assert len(listings) == 4
        names = {l.name for l in listings}
        assert "new-plugin" in names

    def test_skip_underscore_directories(self, tmp_path: Path) -> None:
        """测试跳过以下划线开头的目录。"""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        # 以下划线开头的目录
        hidden_dir = plugins_dir / "_hidden"
        hidden_dir.mkdir()
        manifest_hidden = {"name": "hidden", "version": "1.0.0"}
        (hidden_dir / "manifest.yaml").write_text(yaml.dump(manifest_hidden))

        # 正常目录
        normal_dir = plugins_dir / "normal"
        normal_dir.mkdir()
        manifest_normal = {"name": "normal", "version": "1.0.0"}
        (normal_dir / "manifest.yaml").write_text(yaml.dump(manifest_normal))

        registry = PluginRegistry(plugins_root=plugins_dir)
        listings = registry.scan_local_plugins()
        names = {l.name for l in listings}
        assert "normal" in names
        assert "hidden" not in names, "下划线开头的目录应被跳过"

    def test_category_parsing(self, temp_plugins_dir: Path) -> None:
        """测试分类解析。"""
        registry = PluginRegistry(plugins_root=temp_plugins_dir)
        listings = registry.scan_local_plugins()

        categories = {l.name: l.category for l in listings}
        assert categories["token-manager"] == PluginCategory.INFRASTRUCTURE
        assert categories["data-exporter"] == PluginCategory.DATA_ANALYTICS
        assert categories["ai-assistant"] == PluginCategory.AI_TOOLS
