"""DDW LLM Gateway — Plugin entry point (lightweight mode)."""

from __future__ import annotations

import logging
from typing import Any

from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    name = "ddw_llm_gateway_plugin"
    version = "1.0.0"
    description = "LLM 统一网关插件 — 渠道管理、负载均衡、失败重试、流式转发"
    router_prefix = "/api/v1/plugins/ddw-llm-gateway"

    def __init__(
        self,
        app: Any = None,
        config: dict[str, Any] | None = None,
        manifest: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(app=app, config=config, manifest=manifest)
        for key, value in kwargs.items():
            setattr(self, key, value)

    def setup(self) -> None:
        """Register routes on the host app."""
        from . import register
        register(self.app)
        logger.info("ddw_llm_gateway_plugin registered")


__all__ = ["Plugin"]
