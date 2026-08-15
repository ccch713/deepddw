"""DDW 指标口径字典插件（PluginBase）"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from plugins.ddw_metric_dict import PLUGIN_NAME, VERSION
from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    name = PLUGIN_NAME
    version = VERSION
    router_prefix = f"/api/v1/plugins/{PLUGIN_NAME}"

    def __init__(self, app=None, config=None, manifest=None, **kwargs):
        super().__init__(app=app, config=config, manifest=manifest)

    def setup(self) -> None:
        from plugins.ddw_metric_dict.router import build_router
        self._router: APIRouter = build_router(self)
        self.app.include_router(self._router)
        logger.info("ddw-metric-dict %s initialized", VERSION)


__all__ = ["Plugin"]
