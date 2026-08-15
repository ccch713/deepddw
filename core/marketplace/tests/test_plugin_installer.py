"""插件安装器测试。

测试安装/卸载/启停和 manifest 验证功能。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.marketplace.plugin_installer import PluginInstaller


class TestPluginInstaller:
    """插件安装器核心功能测试。"""

    def test_validate_manifest_valid(self) -> None:
        """测试验证有效 manifest。"""
        installer = PluginInstaller()
        manifest = {
            "name": "test-plugin",
            "version": "1.0.0",
            "description": "测试插件",
            "permissions": ["database"],
            "dependencies": {},
        }
        result = installer.validate_manifest(manifest)
        assert result["valid"] is True
        assert result["errors"] == []

    def test_validate_manifest_missing_name(self) -> None:
        """测试验证缺少 name 的 manifest。"""
        installer = PluginInstaller()
        manifest = {"version": "1.0.0"}
        result = installer.validate_manifest(manifest)
        assert result["valid"] is False
        assert any("name" in e for e in result["errors"])

    def test_validate_manifest_missing_version(self) -> None:
        """测试验证缺少 version 的 manifest。"""
        installer = PluginInstaller()
        manifest = {"name": "test-plugin"}
        result = installer.validate_manifest(manifest)
        assert result["valid"] is False
        assert any("version" in e for e in result["errors"])

    def test_validate_manifest_invalid_name_format(self) -> None:
        """测试验证非法名称格式。"""
        installer = PluginInstaller()
        manifest = {"name": "test plugin!", "version": "1.0.0"}
        result = installer.validate_manifest(manifest)
        assert result["valid"] is False
        assert any("name" in e for e in result["errors"])

    def test_validate_manifest_invalid_permissions_type(self) -> None:
        """测试验证非法权限类型。"""
        installer = PluginInstaller()
        manifest = {
            "name": "test-plugin",
            "version": "1.0.0",
            "permissions": "database",  # 应该是列表
        }
        result = installer.validate_manifest(manifest)
        assert result["valid"] is False
        assert any("permissions" in e for e in result["errors"])

    def test_validate_manifest_invalid_dependencies_type(self) -> None:
        """测试验证非法依赖类型。"""
        installer = PluginInstaller()
        manifest = {
            "name": "test-plugin",
            "version": "1.0.0",
            "dependencies": ["other-plugin"],  # 应该是字典
        }
        result = installer.validate_manifest(manifest)
        assert result["valid"] is False
        assert any("dependencies" in e for e in result["errors"])

    def test_validate_manifest_non_semver_version(self) -> None:
        """测试非 semver 版本格式（警告而非错误）。"""
        installer = PluginInstaller()
        manifest = {"name": "test-plugin", "version": "1.0"}
        result = installer.validate_manifest(manifest)
        assert result["valid"] is True
        assert len(result["warnings"]) > 0

    def test_validate_manifest_empty(self) -> None:
        """测试空 manifest。"""
        installer = PluginInstaller()
        result = installer.validate_manifest({})
        assert result["valid"] is False
        assert len(result["errors"]) >= 2  # name 和 version 都缺失

    def test_validate_manifest_with_dict_permissions(self) -> None:
        """测试权限为字典格式的 manifest。"""
        installer = PluginInstaller()
        manifest = {
            "name": "test-plugin",
            "version": "1.0.0",
            "permissions": {"database": True, "config": True},
        }
        result = installer.validate_manifest(manifest)
        assert result["valid"] is True

    @pytest.mark.asyncio
    async def test_install_plugin_not_found(self) -> None:
        """测试安装不存在的插件。"""
        installer = PluginInstaller()

        with patch(
            "core.marketplace.plugin_installer.get_plugin_registry"
        ) as mock_registry:
            mock_registry.return_value.get_plugin_detail.return_value = None

            result = await installer.install_plugin("nonexistent")
            assert result["success"] is False
            assert "不存在" in result["message"]

    @pytest.mark.asyncio
    async def test_install_plugin_manifest_validation_fails(self) -> None:
        """测试安装 manifest 验证失败的插件。"""
        installer = PluginInstaller()

        mock_listing = MagicMock()
        mock_listing.name = "bad-plugin"
        mock_listing.version = "1.0.0"
        mock_listing.manifest_raw = {"version": "1.0.0"}  # 缺少 name

        with patch(
            "core.marketplace.plugin_installer.get_plugin_registry"
        ) as mock_registry:
            mock_registry.return_value.get_plugin_detail.return_value = mock_listing

            result = await installer.install_plugin("bad-plugin")
            assert result["success"] is False
            assert "验证失败" in result["message"]

    @pytest.mark.asyncio
    async def test_uninstall_plugin_not_installed(self) -> None:
        """测试卸载未安装的插件。"""
        installer = PluginInstaller()

        with patch.object(installer, "_get_install_record", return_value=None):
            result = await installer.uninstall_plugin("nonexistent")
            assert result["success"] is False
            assert "未安装" in result["message"]

    @pytest.mark.asyncio
    async def test_enable_plugin_not_installed(self) -> None:
        """测试启用未安装的插件。"""
        installer = PluginInstaller()

        with patch.object(installer, "_get_install_record", return_value=None):
            result = await installer.enable_plugin("nonexistent")
            assert result["success"] is False
            assert "未安装" in result["message"]

    @pytest.mark.asyncio
    async def test_enable_plugin_already_enabled(self) -> None:
        """测试启用已启用的插件。"""
        installer = PluginInstaller()

        mock_record = MagicMock()
        mock_record.enabled = True

        with patch.object(installer, "_get_install_record", return_value=mock_record):
            result = await installer.enable_plugin("test-plugin")
            assert result["success"] is False
            assert "已启用" in result["message"]

    @pytest.mark.asyncio
    async def test_disable_plugin_not_installed(self) -> None:
        """测试禁用未安装的插件。"""
        installer = PluginInstaller()

        with patch.object(installer, "_get_install_record", return_value=None):
            result = await installer.disable_plugin("nonexistent")
            assert result["success"] is False
            assert "未安装" in result["message"]

    @pytest.mark.asyncio
    async def test_disable_plugin_already_disabled(self) -> None:
        """测试禁用已禁用的插件。"""
        installer = PluginInstaller()

        mock_record = MagicMock()
        mock_record.enabled = False

        with patch.object(installer, "_get_install_record", return_value=mock_record):
            result = await installer.disable_plugin("test-plugin")
            assert result["success"] is False
            assert "已禁用" in result["message"]
