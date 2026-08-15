from __future__ import annotations

"""DDW 岗位设计器插件 Plugin 类。"""

import logging

from sdk.plugin_base import PluginBase

from . import PLUGIN_NAME, VERSION
from . import models as _models  # noqa: F401
from .router import build_router

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """岗位设计器插件主类。"""

    name = PLUGIN_NAME
    version = VERSION
    router_prefix = f"/api/v1/plugins/{PLUGIN_NAME}"

    def setup(self) -> None:
        """注册路由。"""
        self._router = build_router()
        self.app.include_router(self._router)
        logger.info("%s plugin %s initialized", PLUGIN_NAME, VERSION)


__all__ = ["Plugin"]
