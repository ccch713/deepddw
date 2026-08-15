"""DDW NHC/EU/EFSA/FDA法规证据链管理 — Plugin entry point for DDW AI Hub loader."""
from __future__ import annotations

import logging

from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """NHC/EU/EFSA/FDA法规证据链管理"""

    name = "ddw-regulatory-evidence"
    version = "1.0.0"
    router_prefix = "/api/v1/plugins/ddw-regulatory-evidence"

    def setup(self) -> None:
        """Register FastAPI router on the host app."""
        from .router import router
        self._router = router
        self.app.include_router(router)
        logger.info("ddw-regulatory-evidence v1.0.0 registered")


__all__ = ["Plugin"]
