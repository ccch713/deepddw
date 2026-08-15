"""DDW 企业微信插件 Plugin 类。"""

from __future__ import annotations

import logging

from sdk.plugin_base import PluginBase

from . import PLUGIN_NAME, VERSION
from .router import build_router

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """企业微信 OAuth 免登集成插件主类。"""

    name = PLUGIN_NAME
    version = VERSION
    router_prefix = f"/api/v1/plugins/{PLUGIN_NAME}"

    def setup(self) -> None:
        router = build_router()
        self._router = router
        self.app.include_router(router)
        logger.info("ddw-wecom plugin %s initialized", VERSION)


__all__ = ["Plugin"]
