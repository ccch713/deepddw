"""DDW 口腔诊所 AI 客服插件 — 武汉东华口腔青山店.

基于知识库 RAG 检索 + 平台 LLM 网关,
无外部依赖，纯 stdlib 实现。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PLUGIN_NAME = "ddw_clinic_cs"
PLUGIN_VERSION = "0.1.0"


class Plugin:
    """口腔诊所 AI 客服插件 — 患者咨询 API."""

    name = PLUGIN_NAME
    version = PLUGIN_VERSION
    router_prefix = "/api/v1/plugins/ddw_clinic_cs"

    def setup(self) -> None:
        """Register FastAPI router on the host app."""
        from .router import router

        self._router = router
        self.app.include_router(router)
        logger.info("ddw_clinic_cs v%s registered", PLUGIN_VERSION)


__all__ = ["Plugin"]
