"""DDW KPI 插件（PluginBase）"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from plugins.ddw_kpi import PLUGIN_NAME, VERSION
from plugins.ddw_kpi.subscribers.training_events import setup_kpi_subscribers
from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)

class Plugin(PluginBase):
    name = PLUGIN_NAME
    version = VERSION
    router_prefix = f"/api/v1/plugins/{PLUGIN_NAME}"
    def setup(self) -> None:
        from plugins.ddw_kpi.router import build_router
        self._router: APIRouter = build_router(self)
        self.app.include_router(self._router)
        setup_kpi_subscribers(self)
        logger.info("ddw-kpi %s initialized", VERSION)
__all__ = ["Plugin"]
