from __future__ import annotations

"""DDW 应收实收核销插件 Plugin 类（DDW AI Hub — 销售端 CRM P1-5）。"""

import logging

from sdk.plugin_base import PluginBase

from . import PLUGIN_NAME, VERSION
from .router import build_router

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """应收实收核销插件主类。

    本插件是跨 P1-3 / P1-4 的业务操作插件，**不创建新表**。
    setup() 阶段只注册路由；模型注册由 services.py 内部 import 触发
    （通过 plugins.ddw_receivable.models / plugins.ddw_offline_pos.models）。
    """

    name = PLUGIN_NAME
    version = VERSION
    router_prefix = f"/api/v1/plugins/{PLUGIN_NAME}"

    def setup(self) -> None:
        """注册路由。"""
        self._router = build_router()
        self.app.include_router(self._router)
        logger.info("ddw-reconciliation plugin %s initialized", VERSION)


__all__ = ["Plugin"]
