"""DDW ESG ESG Assessment — Plugin entry point (lightweight mode)."""

from __future__ import annotations

import logging

from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    name = "ddw_esg_assessment"
    version = "1.0.0"
    router_prefix = "/api/v1/plugins/ddw-esg-assessment"

    def setup(self) -> None:
        """Register routes on the host app."""
        from . import register
        register(self.app)
        self._router = getattr(register, "_router", None)
        logger.info("ddw_esg_assessment registered")


__all__ = ["Plugin"]
