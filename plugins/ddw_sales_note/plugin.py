from __future__ import annotations

"""DDW 拜访与沟通记录插件 Plugin 类（DDW AI Hub — 销售端 CRM P3-2）。"""

import logging

from sdk.plugin_base import PluginBase

from . import PLUGIN_NAME, VERSION
from . import models as _models  # noqa: F401
from .router import build_router

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """拜访与沟通记录插件主类。"""

    name = PLUGIN_NAME
    version = VERSION
    router_prefix = f"/api/v1/plugins/{PLUGIN_NAME}"

    def setup(self) -> None:
        """注册路由。"""
        self._router = build_router()
        self.app.include_router(self._router)
        logger.info("ddw-sales-note plugin %s initialized", VERSION)


__all__ = ["Plugin"]
