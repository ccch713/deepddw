"""插件安装/卸载逻辑。

职责：
1. 安装/升级/卸载插件
2. 启用/禁用插件
3. 验证 manifest 合规性
4. 调用 PluginManager 执行实际加载/卸载
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Optional

from sqlalchemy import select

from core.database.factory import get_engine_factory
from core.marketplace.models import PluginInstall
from core.marketplace.plugin_registry import get_plugin_registry
from core.plugin_manager.manager import get_plugin_manager

logger = logging.getLogger(__name__)


class PluginInstaller:
    """插件安装器 — 处理安装/卸载/启停逻辑。

    协调 PluginManager（运行时加载）和数据库（持久化状态），
    确保两者的安装状态保持一致。
    """

    async def install_plugin(
        self, name: str, version: Optional[str] = None, force: bool = False
    ) -> dict:
        """安装或升级插件。

        Args:
            name: 插件名称。
            version: 指定版本（None 表示最新）。
            force: 是否强制重装。

        Returns:
            操作结果字典。
        """
        # 1. 从注册表获取插件信息
        registry = get_plugin_registry()
        listing = registry.get_plugin_detail(name)
        if not listing:
            return {"success": False, "message": f"插件 '{name}' 不存在", "action": "install"}

        target_version = version or listing.version

        # 2. 验证 manifest
        validation = self.validate_manifest(listing.manifest_raw or {})
        if not validation["valid"]:
            return {
                "success": False,
                "message": f"manifest 验证失败: {'; '.join(validation['errors'])}",
                "action": "install",
            }

        # 3. 检查是否已安装
        existing = await self._get_install_record(name)
        if existing and not force:
            if existing.version == target_version:
                return {
                    "success": False,
                    "message": f"插件 '{name}' v{target_version} 已安装",
                    "action": "install",
                }
            # 升级逻辑
            logger.info("升级插件 %s: %s -> %s", name, existing.version, target_version)

        # 4. 调用 PluginManager 加载模块
        pm = get_plugin_manager()
        try:
            # 先注册
            manifests = pm.discover()
            manifest_names = {m.name for m in manifests}
            if name not in manifest_names:
                return {
                    "success": False,
                    "message": f"插件 '{name}' 未在 plugins/ 目录中找到",
                    "action": "install",
                }

            # 注册所有插件
            await pm.register_all()
            # 加载目标模块
            await pm.load_module(name)
        except Exception as exc:  # noqa: BLE001
            logger.exception("加载插件模块失败: %s", name)
            return {"success": False, "message": f"加载失败: {exc}", "action": "install"}

        # 5. 持久化安装记录
        await self._upsert_install_record(
            name=name,
            version=target_version,
            enabled=True,
            isolation=listing.manifest_raw.get("isolation", "inline") if listing.manifest_raw else "inline",
        )

        # 6. 更新下载计数
        await self._increment_downloads(name)

        return {
            "success": True,
            "message": f"插件 '{name}' v{target_version} 安装成功",
            "action": "install",
        }

    async def uninstall_plugin(self, name: str) -> dict:
        """卸载插件。

        Args:
            name: 插件名称。

        Returns:
            操作结果字典。
        """
        # 1. 检查是否已安装
        existing = await self._get_install_record(name)
        if not existing:
            return {"success": False, "message": f"插件 '{name}' 未安装", "action": "uninstall"}

        # 2. 调用 PluginManager 卸载
        pm = get_plugin_manager()
        try:
            await pm.uninstall(name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("PluginManager 卸载警告: %s", exc)

        # 3. 删除安装记录
        factory = get_engine_factory()
        async with factory.session("main") as session:
            result = await session.execute(
                select(PluginInstall).where(PluginInstall.plugin_name == name)
            )
            record = result.scalar_one_or_none()
            if record:
                await session.delete(record)

        return {
            "success": True,
            "message": f"插件 '{name}' 已卸载",
            "action": "uninstall",
        }

    async def enable_plugin(self, name: str) -> dict:
        """启用插件。

        Args:
            name: 插件名称。

        Returns:
            操作结果字典。
        """
        existing = await self._get_install_record(name)
        if not existing:
            return {"success": False, "message": f"插件 '{name}' 未安装", "action": "enable"}

        if existing.enabled:
            return {"success": False, "message": f"插件 '{name}' 已启用", "action": "enable"}

        # 更新数据库
        factory = get_engine_factory()
        async with factory.session("main") as session:
            result = await session.execute(
                select(PluginInstall).where(PluginInstall.plugin_name == name)
            )
            record = result.scalar_one_or_none()
            if record:
                record.enabled = True

        # 调用 PluginManager
        pm = get_plugin_manager()
        try:
            await pm.enable(name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("PluginManager 启用警告: %s", exc)

        return {"success": True, "message": f"插件 '{name}' 已启用", "action": "enable"}

    async def disable_plugin(self, name: str) -> dict:
        """禁用插件。

        Args:
            name: 插件名称。

        Returns:
            操作结果字典。
        """
        existing = await self._get_install_record(name)
        if not existing:
            return {"success": False, "message": f"插件 '{name}' 未安装", "action": "disable"}

        if not existing.enabled:
            return {"success": False, "message": f"插件 '{name}' 已禁用", "action": "disable"}

        # 更新数据库
        factory = get_engine_factory()
        async with factory.session("main") as session:
            result = await session.execute(
                select(PluginInstall).where(PluginInstall.plugin_name == name)
            )
            record = result.scalar_one_or_none()
            if record:
                record.enabled = False

        # 调用 PluginManager
        pm = get_plugin_manager()
        try:
            await pm.disable(name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("PluginManager 禁用警告: %s", exc)

        return {"success": True, "message": f"插件 '{name}' 已禁用", "action": "disable"}

    # ------------------------------------------------------------------ #
    # Manifest 验证
    # ------------------------------------------------------------------ #

    def validate_manifest(self, manifest: dict) -> dict:
        """验证 manifest 合规性。

        Args:
            manifest: 原始 manifest 字典。

        Returns:
            {"valid": bool, "errors": [str], "warnings": [str]}
        """
        errors: list[str] = []
        warnings: list[str] = []

        # 必填字段检查
        if not manifest.get("name"):
            errors.append("缺少必填字段: name")
        if not manifest.get("version"):
            errors.append("缺少必填字段: version")

        # name 格式检查
        name = manifest.get("name", "")
        if name and not all(c.isalnum() or c in "-_" for c in name):
            errors.append("name 只能包含字母、数字、连字符和下划线")

        # version 格式检查（简单 semver）
        version = manifest.get("version", "")
        if version:
            parts = version.split(".")
            if len(parts) < 3:
                warnings.append("version 建议使用完整 semver 格式 (如 1.0.0)")
            elif not all(p.isdigit() for p in parts):
                warnings.append("version 各部分应为数字")

        # permissions 类型检查
        permissions = manifest.get("permissions", [])
        if permissions and not isinstance(permissions, (list, dict)):
            errors.append("permissions 必须是列表或字典")

        # dependencies 格式检查
        deps = manifest.get("dependencies", {})
        if deps and not isinstance(deps, dict):
            errors.append("dependencies 必须是字典")

        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    # ------------------------------------------------------------------ #
    # 内部辅助方法
    # ------------------------------------------------------------------ #

    async def _get_install_record(self, name: str) -> Optional[PluginInstall]:
        """查询安装记录。"""
        factory = get_engine_factory()
        async with factory.session("main") as session:
            result = await session.execute(
                select(PluginInstall).where(PluginInstall.plugin_name == name)
            )
            return result.scalar_one_or_none()

    async def _upsert_install_record(
        self,
        name: str,
        version: str,
        enabled: bool = True,
        isolation: str = "inline",
    ) -> None:
        """插入或更新安装记录。"""
        factory = get_engine_factory()
        async with factory.session("main") as session:
            result = await session.execute(
                select(PluginInstall).where(PluginInstall.plugin_name == name)
            )
            record = result.scalar_one_or_none()
            if record:
                record.version = version
                record.enabled = enabled
                record.isolation = isolation
                record.updated_at = dt.datetime.now(dt.timezone.utc)
            else:
                record = PluginInstall(
                    plugin_name=name,
                    version=version,
                    enabled=enabled,
                    isolation=isolation,
                )
                session.add(record)

    async def _increment_downloads(self, name: str) -> None:
        """增加插件下载计数。"""
        factory = get_engine_factory()
        async with factory.session("main") as session:
            from core.marketplace.models import PluginListing

            result = await session.execute(
                select(PluginListing).where(PluginListing.name == name)
            )
            listing = result.scalar_one_or_none()
            if listing:
                listing.downloads += 1


# --------------------------------------------------------------------------- #
# 单例
# --------------------------------------------------------------------------- #

_installer: Optional[PluginInstaller] = None


def get_plugin_installer() -> PluginInstaller:
    """获取全局插件安装器单例。"""
    global _installer
    if _installer is None:
        _installer = PluginInstaller()
    return _installer
