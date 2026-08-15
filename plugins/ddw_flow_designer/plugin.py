"""碳硅协同插件 Plugin 类。"""

from __future__ import annotations

import logging

from sdk.plugin_base import PluginBase

from . import PLUGIN_NAME, VERSION
from . import models as _models  # noqa: F401  触发模型注册到 Base.metadata
from .router import build_router

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """碳硅协作空间插件主类。"""

    name = PLUGIN_NAME
    version = VERSION

    def setup(self) -> None:
        """注册路由。"""
        self._router = build_router()
        self.app.include_router(self._router)
        logger.info("ddw-flow-designer plugin %s initialized", VERSION)


__all__ = ["Plugin"]
