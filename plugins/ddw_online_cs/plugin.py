"""DDW 在线客服插件 — Plugin entry point for DDW AI Hub loader."""
from __future__ import annotations

import logging

from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """在线客服：RAG 知识库 + 平台 LLM 网关."""

    name = "ddw_online_cs"
    version = "2.0.0"
    router_prefix = "/api/v1/plugins/ddw_online_cs"

    def setup(self) -> None:
        """Register FastAPI router on the host app."""
        from .router import router
        self._router = router
        self.app.include_router(router)
        logger.info("ddw_online_cs v1.0.0 registered")


__all__ = ["Plugin"]
