"""ddw_memory_knowledge_bridge Plugin 类。"""
from __future__ import annotations

import logging

from sdk.plugin_base import PluginBase

from . import PLUGIN_NAME, VERSION
from .router import build_router

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    name = PLUGIN_NAME
    version = VERSION

    def __init__(self, app=None, config=None, manifest=None, **kwargs):
        super().__init__(app=app, config=config, manifest=manifest)

    def setup(self) -> None:
        router = build_router()
        self._router = router
        if self.app:
            self.app.include_router(router)
        logger.info("ddw-memory-knowledge-bridge plugin %s initialized", VERSION)


__all__ = ["Plugin"]
