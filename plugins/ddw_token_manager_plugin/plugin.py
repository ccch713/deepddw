"""DDW Token Manager — Plugin entry point (lightweight mode)."""

from __future__ import annotations

import logging

from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    name = "ddw_token_manager_plugin"
    version = "1.0.0"
    router_prefix = "/api/v1/plugins/ddw-token-manager"

    def setup(self) -> None:
        """Register routes on the host app."""
        from .main import register
        register(self.app)
        logger.info("ddw_token_manager_plugin registered")


__all__ = ["Plugin"]
