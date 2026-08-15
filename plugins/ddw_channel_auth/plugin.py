"""DDW 渠道授权与结算插件 Plugin 类。"""

from __future__ import annotations

import logging

from sdk.plugin_base import PluginBase

from . import PLUGIN_NAME, VERSION
from .router import build_router

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """渠道授权与结算插件主类。"""

    name = PLUGIN_NAME
    version = VERSION
    router_prefix = "/api/v1/plugins/ddw-channel-auth"

    def setup(self) -> None:
        """注册路由。"""
        self._router = build_router()
        self.app.include_router(self._router)
        logger.info("ddw-channel-auth plugin %s initialized", VERSION)


__all__ = ["Plugin"]
