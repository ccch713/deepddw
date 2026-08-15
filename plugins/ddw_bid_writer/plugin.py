"""DDW 投标标书插件 Plugin 类。"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from plugins.ddw_bid_writer import PLUGIN_NAME, VERSION

# 触发 models 注册到 Base.metadata（确保 init_db() 能建表）
from plugins.ddw_bid_writer import models as _models  # noqa: F401
from plugins.ddw_bid_writer.services import (
    GenerateService,
    ReviewService,
    StyleService,
    TemplateService,
)
from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    name = PLUGIN_NAME
    version = VERSION
    router_prefix = f"/api/v1/plugins/{PLUGIN_NAME}"

    def setup(self) -> None:
        use_llm = bool(self.config.get("use_llm", False))
        self.template_service = TemplateService()
        self.generate_service = GenerateService(use_llm=use_llm)
        self.style_service = StyleService()
        self.review_service = ReviewService()

        from plugins.ddw_bid_writer.router import build_router

        self._router: APIRouter = build_router(self)
        self.app.include_router(self._router)
        logger.info("ddw-bid-writer plugin %s initialized (use_llm=%s)", VERSION, use_llm)


__all__ = ["Plugin"]
