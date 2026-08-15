from __future__ import annotations

"""DDW 财务看板插件 Plugin 类（DDW AI Hub — 销售端 CRM P1-6）。"""

import logging

from sdk.plugin_base import PluginBase

from . import PLUGIN_NAME, VERSION
from .router import build_router

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """财务看板插件主类。"""

    name = PLUGIN_NAME
    version = VERSION
    router_prefix = f"/api/v1/plugins/{PLUGIN_NAME}"

    def setup(self) -> None:
        """注册路由。

        本插件是聚合查询插件，不创建新表，因此不需要 import 自身 models.py。
        但路由会引用 P1-1 / P1-3 / P1-4 的模型，由 services.py 内部 import
        触发注册到 Base.metadata。
        """
        self._router = build_router()
        self.app.include_router(self._router)
        logger.info("ddw-finance-dashboard plugin %s initialized", VERSION)


__all__ = ["Plugin"]
