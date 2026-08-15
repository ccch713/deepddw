"""DDW 业务指标仪表盘插件 Plugin 类。"""

from __future__ import annotations

import logging

from sdk.plugin_base import PluginBase

from . import PLUGIN_NAME, VERSION
from .router import build_router

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """业务指标仪表盘插件主类。"""

    name = PLUGIN_NAME
    version = VERSION
    router_prefix = f"/api/v1/plugins/{PLUGIN_NAME}"

    def setup(self) -> None:
        """注册路由。

        本插件是聚合查询插件，不创建新表。
        路由会引用其他插件的模型，由 services.py 内部 import 触发注册。
        """
        self._router = build_router()
        self.app.include_router(self._router)
        logger.info("ddw-business-metrics plugin %s initialized", VERSION)


__all__ = ["Plugin"]
