from __future__ import annotations

"""DDW 实例绑定插件 Plugin 类（DDW AI Hub — 销售端 CRM P4-3）。"""

import logging

from sdk.plugin_base import PluginBase

from . import PLUGIN_NAME, VERSION
from . import models as _models  # noqa: F401  触发模型注册到 Base.metadata
from .router import build_router

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """实例绑定插件主类。"""

    name = PLUGIN_NAME
    version = VERSION
    router_prefix = f"/api/v1/plugins/{PLUGIN_NAME}"

    def setup(self) -> None:
        """注册路由。"""
        self._router = build_router()
        self.app.include_router(self._router)
        logger.info("ddw-instance-binding plugin %s initialized", VERSION)


__all__ = ["Plugin"]
