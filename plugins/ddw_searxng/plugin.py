"""DDW SearXNG 插件 Plugin 类。"""

from __future__ import annotations

import logging

from sdk.plugin_base import PluginBase

from . import PLUGIN_NAME, VERSION
from .router import build_router

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """SearXNG 聚合搜索插件。"""

    name = PLUGIN_NAME
    version = VERSION
    router_prefix = f"/api/v1/plugins/{PLUGIN_NAME}"

    def setup(self) -> None:
        """挂载路由（router 由 PluginBase.register() 统一 include，避免重复注册）。"""
        self._router = build_router()
        logger.info("ddw-searxng plugin %s initialized", VERSION)


__all__ = ["Plugin"]
