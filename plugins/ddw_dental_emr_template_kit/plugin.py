"""DDW Dental EMR Template Kit - Plugin 入口."""
from __future__ import annotations

import logging
from typing import Any, Optional

from sdk.plugin_base import PluginBase

from . import loader
from .router import router

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    name = "ddw_dental_emr_template_kit"
    version = "0.1.0"
    description = "9 类口腔诊疗病历模板套件"

    def __init__(self, app: Any = None, config: Optional[dict] = None, manifest: Any = None, **kwargs) -> None:
        super().__init__(app, config)
        self._router = None

    async def initialize(self) -> None:
        templates = loader.list_templates()
        logger.info(
            "ddw_dental_emr_template_kit initialized: %d templates loaded", len(templates)
        )

    async def start(self) -> None:
        logger.info("ddw_dental_emr_template_kit started")

    async def stop(self) -> None:
        logger.info("ddw_dental_emr_template_kit stopped")

    def setup(self) -> None:
        self._router = router
        if self.app is not None and hasattr(self.app, "include_router"):
            self.app.include_router(router)
