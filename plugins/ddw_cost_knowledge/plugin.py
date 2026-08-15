"""DDW 造价知识库插件 Plugin 类。"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from plugins.ddw_cost_knowledge import PLUGIN_NAME, VERSION

# 触发 models 注册到 Base.metadata（确保 init_db() 能建表）
from plugins.ddw_cost_knowledge import models as _models  # noqa: F401
from plugins.ddw_cost_knowledge.services import (
    EstimateService,
    ExtractService,
    ImportService,
    SearchService,
)
from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    name = PLUGIN_NAME
    version = VERSION
    router_prefix = f"/api/v1/plugins/{PLUGIN_NAME}"

    def setup(self) -> None:
        upload_dir = self.config.get("upload_dir", "./data/uploads/cost")
        max_search = int(self.config.get("max_search_results", 20))

        self.import_service = ImportService(upload_dir=upload_dir)
        self.extract_service = ExtractService()
        self.estimate_service = EstimateService()
        self.search_service = SearchService(max_results=max_search)

        from plugins.ddw_cost_knowledge.router import build_router

        self._router: APIRouter = build_router(self)
        self.app.include_router(self._router)
        logger.info("ddw-cost-knowledge plugin %s initialized", VERSION)


__all__ = ["Plugin"]
