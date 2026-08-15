"""DDW ISO22000/FSSC22000/HACCP/SOP/法规智能检索 — Plugin entry point for DDW AI Hub loader."""
from __future__ import annotations

import logging

from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """ISO22000/FSSC22000/HACCP/SOP/法规智能检索"""

    name = "ddw-quality-knowledge"
    version = "1.0.0"
    router_prefix = "/api/v1/plugins/ddw-quality-knowledge"

    def setup(self) -> None:
        """Register FastAPI router on the host app."""
        from .router import router
        self._router = router
        self.app.include_router(router)
        logger.info("ddw-quality-knowledge v1.0.0 registered")


__all__ = ["Plugin"]
