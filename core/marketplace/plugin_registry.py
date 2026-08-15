"""插件注册表 — 本地扫描 + 市场元数据缓存。

职责：
1. 扫描 plugins/ 目录发现所有可用插件
2. 从本地 manifest.yaml 解析元数据并缓存
3. 提供统一的插件列表和详情查询接口
4. 支持按分类/标签/名称过滤
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from core.marketplace.models import PluginListing
from core.marketplace.plugin_market import PluginCategory

logger = logging.getLogger(__name__)

# 插件根目录（与 PluginManager 保持一致）
PLUGINS_ROOT = Path(__file__).resolve().parent.parent.parent / "plugins"

# 缓存 TTL（秒）
_CACHE_TTL = 300  # 5 分钟


class PluginRegistry:
    """插件注册表 — 扫描、缓存、查询。

    通过扫描 plugins/*/manifest.yaml 发现本地插件，
    解析元数据并维护内存缓存，提供列表和详情查询。
    """

    def __init__(self, plugins_root: Optional[Path] = None) -> None:
        self.plugins_root = plugins_root or PLUGINS_ROOT
        self._cache: Dict[str, PluginListing] = {}
        self._cache_ts: float = 0.0

    # ------------------------------------------------------------------ #
    # 扫描与缓存
    # ------------------------------------------------------------------ #

    def scan_local_plugins(self) -> List[PluginListing]:
        """扫描 plugins/ 目录，发现所有可用插件。

        Returns:
            插件列表，每个元素包含从 manifest.yaml 解析的元数据。
        """
        now = time.time()
        if self._cache and (now - self._cache_ts) < _CACHE_TTL:
            return list(self._cache.values())

        listings: Dict[str, PluginListing] = {}

        if not self.plugins_root.exists():
            logger.warning("插件目录不存在: %s", self.plugins_root)
            return []

        for child in sorted(self.plugins_root.iterdir()):
            if not child.is_dir() or child.name.startswith("_"):
                continue
            manifest_path = child / "manifest.yaml"
            if not manifest_path.exists():
                continue
            try:
                listing = self._parse_manifest(manifest_path)
                if listing:
                    listings[listing.name] = listing
            except Exception as exc:  # noqa: BLE001
                logger.warning("解析插件 manifest 失败 %s: %s", manifest_path, exc)

        self._cache = listings
        self._cache_ts = now
        logger.info("注册表扫描完成，发现 %d 个插件", len(listings))
        return list(listings.values())

    def _parse_manifest(self, manifest_path: Path) -> Optional[PluginListing]:
        """从 manifest.yaml 解析插件元数据。

        Args:
            manifest_path: manifest.yaml 的路径。

        Returns:
            解析后的 PluginListing，格式异常时返回 None。
        """
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        if not data.get("name"):
            logger.warning("manifest.yaml 缺少 name 字段: %s", manifest_path)
            return None

        # 解析分类
        category_str = data.get("ecosystem", {}).get("category", "other")
        try:
            category = PluginCategory(category_str)
        except ValueError:
            category = PluginCategory.OTHER

        # 解析权限列表
        permissions = data.get("permissions", [])
        if isinstance(permissions, dict):
            permissions = list(permissions.keys())

        # 解析标签
        tags = data.get("ecosystem", {}).get("tags", [])
        if isinstance(tags, str):
            tags = [tags]

        return PluginListing(
            name=data["name"],
            version=data.get("version", "0.0.1"),
            description=data.get("description", ""),
            author=data.get("author", "Unknown"),
            license=data.get("license", "MIT"),
            category=category,
            rating=0.0,
            downloads=0,
            tags=tags,
            engine=data.get("engine", ">=0.1.0"),
            permissions=permissions,
            dependencies=data.get("dependencies", {}),
            config_schema=data.get("config_schema"),
            manifest_raw=data,
        )

    def refresh_registry(self) -> List[PluginListing]:
        """强制刷新注册表缓存。

        Returns:
            刷新后的插件列表。
        """
        self._cache.clear()
        self._cache_ts = 0.0
        return self.scan_local_plugins()

    # ------------------------------------------------------------------ #
    # 查询接口
    # ------------------------------------------------------------------ #

    def get_plugin_listings(
        self,
        category: Optional[PluginCategory] = None,
        search: Optional[str] = None,
        installed_names: Optional[set[str]] = None,
    ) -> List[PluginListing]:
        """获取所有可用插件列表，支持过滤。

        Args:
            category: 按分类过滤。
            search: 按名称/描述搜索。
            installed_names: 已安装插件名称集合（用于标记状态）。

        Returns:
            过滤后的插件列表。
        """
        listings = self.scan_local_plugins()
        result: List[PluginListing] = []

        for listing in listings:
            # 分类过滤
            if category and listing.category != category:
                continue
            # 搜索过滤
            if search:
                search_lower = search.lower()
                if (
                    search_lower not in listing.name.lower()
                    and search_lower not in (listing.description or "").lower()
                ):
                    continue
            result.append(listing)

        return result

    def get_plugin_detail(self, name: str) -> Optional[PluginListing]:
        """获取单个插件详情。

        Args:
            name: 插件名称。

        Returns:
            插件详情，不存在时返回 None。
        """
        self.scan_local_plugins()  # 确保缓存已加载
        return self._cache.get(name)


# --------------------------------------------------------------------------- #
# 单例
# --------------------------------------------------------------------------- #

_registry: Optional[PluginRegistry] = None


def get_plugin_registry() -> PluginRegistry:
    """获取全局插件注册表单例。"""
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry
