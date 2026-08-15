"""DDW AI Readiness 插件 Plugin 类。"""

from __future__ import annotations

import logging

from sdk.plugin_base import PluginBase

from . import PLUGIN_NAME, VERSION
from .router import build_router

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """企业 AI 就绪度自评插件。"""

    name = PLUGIN_NAME
    version = VERSION
    router_prefix = f"/api/v1/plugins/{PLUGIN_NAME}"

    def setup(self) -> None:
        self._router = build_router()
        self.app.include_router(self._router)
        logger.info("%s plugin %s initialized", PLUGIN_NAME, VERSION)


__all__ = ["Plugin"]
