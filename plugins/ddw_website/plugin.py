"""DDW 官网插件 — Plugin entry point for DDW AI Hub loader."""
from __future__ import annotations

import logging

from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """官网配置管理：主题模版/站点信息/页面清单."""

    name = "ddw-website"
    version = "1.0.0"
    router_prefix = "/api/v1/plugins/ddw-website"

    def setup(self) -> None:
        """Register FastAPI router on the host app."""
        from .router import router
        self._router = router
        self.app.include_router(router)
        logger.info("ddw-website v1.0.0 registered")


__all__ = ["Plugin"]
