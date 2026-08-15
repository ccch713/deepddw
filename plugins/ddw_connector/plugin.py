"""DDW 连接器元数据发现框架 Plugin 类（DDW AI Hub — AI 层连接器）。"""

from __future__ import annotations

import logging

from sdk.plugin_base import PluginBase

from . import PLUGIN_NAME, VERSION
from .router import build_router

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """连接器元数据发现插件主类。"""

    name = PLUGIN_NAME
    version = VERSION

    def setup(self) -> None:
        """注册路由。"""
        self._router = build_router()
        if self.app is not None:
            self.app.include_router(self._router)
        logger.info("ddw-connector plugin %s initialized", VERSION)


__all__ = ["Plugin"]
