from __future__ import annotations

"""DDW 销售端 AI 副驾驶插件 Plugin 类（DDW AI Hub — 销售端 CRM P3-4）。"""

import logging

from sdk.plugin_base import PluginBase

from . import PLUGIN_NAME, VERSION
from .router import build_router

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """销售端 AI 副驾驶插件主类。"""

    name = PLUGIN_NAME
    version = VERSION
    router_prefix = f"/api/v1/plugins/{PLUGIN_NAME}"

    def setup(self) -> None:
        """注册路由。

        本插件是 AI 能力聚合插件，**不创建新表**，因此不需要 import 自身 models.py。
        路由内部会跨插件 query P0-1~P0-4 / P3-1~P3-2 的 ORM 模型，
        由 services.py 内部 import 触发注册到 Base.metadata。
        """
        self._router = build_router()
        self.app.include_router(self._router)
        logger.info("ddw-sales-copilot plugin %s initialized", VERSION)


__all__ = ["Plugin"]
