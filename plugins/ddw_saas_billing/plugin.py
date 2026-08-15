"""DDW SaaS 计费插件（PluginBase）"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from plugins.ddw_saas_billing import PLUGIN_NAME, VERSION
from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)

class Plugin(PluginBase):
    name = PLUGIN_NAME
    version = VERSION
    router_prefix = f"/api/v1/plugins/{PLUGIN_NAME}"
    def setup(self) -> None:
        from plugins.ddw_saas_billing.router import build_router
        self._router: APIRouter = build_router(self)
        self.app.include_router(self._router)
        logger.info("ddw-saas-billing %s initialized", VERSION)
__all__ = ["Plugin"]
