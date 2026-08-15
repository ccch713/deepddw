"""DDW 口腔诊所 AI 客服 — Plugin entry point for DDW AI Hub loader."""
from __future__ import annotations

import logging

from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """口腔诊所客服：RAG 知识库 + 平台 LLM 网关."""

    name = "ddw_clinic_cs"
    version = "0.1.0"
    router_prefix = "/api/v1/plugins/ddw_clinic_cs"

    def setup(self) -> None:
        """Register FastAPI router on the host app."""
        from .router import router

        self._router = router
        self.app.include_router(router)
        logger.info("ddw_clinic_cs v0.1.0 registered")


__all__ = ["Plugin"]
