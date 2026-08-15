"""DDW 在线客服插件 — 官网联系我们页 AI 客服对话框后端.

基于官网知识库 RAG 检索 + 平台 LLM 网关（minimax→deepseek→ollama 兜底）,
无外部依赖，纯 stdlib 实现。
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

PLUGIN_NAME = "ddw_online_cs"
VERSION = "1.0.0"


class Plugin:
    """在线客服插件 — 客服对话框 API."""

    name = PLUGIN_NAME
    version = VERSION
    router_prefix = "/api/v1/plugins/ddw_online_cs"

    def setup(self) -> None:
        """Register FastAPI router on the host app."""
        from .router import router
        self._router = router
        self.app.include_router(router)
        logger.info("ddw_online_cs v%s registered", VERSION)


__all__ = ["Plugin"]
