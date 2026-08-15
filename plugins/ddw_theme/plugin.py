"""DDW 界面主题系统插件入口"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from plugins.ddw_theme import PLUGIN_NAME, VERSION
from plugins.ddw_theme.service import ThemeService
from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    name = PLUGIN_NAME
    version = VERSION
    router_prefix = f"/api/v1/plugins/{PLUGIN_NAME}"

    def __init__(self, app=None, config=None, manifest=None, **kwargs):
        self.theme_service = ThemeService()
        super().__init__(app, config, manifest)

    def setup(self) -> None:
        from plugins.ddw_theme.router import build_router
        self._router: APIRouter = build_router(self)
        self.app.include_router(self._router)
        logger.info("ddw-theme plugin %s initialized", VERSION)


__all__ = ["Plugin"]
