"""DDW Clinical ASR - Plugin 入口."""
from __future__ import annotations

import logging
from typing import Any, Optional

from sdk.plugin_base import PluginBase

from . import config
from .router import router

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """ddw_clinical_asr 插件."""

    name = "ddw_clinical_asr"
    version = "0.1.0"
    description = "LLM 口腔医疗实体抽取（9 类诊疗）"

    def __init__(self, app: Any = None, config: Optional[dict] = None, manifest: Any = None, **kwargs) -> None:
        super().__init__(app, config)
        self._router = None

    async def initialize(self) -> None:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        config.PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(
            "ddw_clinical_asr initialized: model=%s, prompts_dir=%s",
            config.DEFAULT_MODEL,
            config.PROMPTS_DIR,
        )

    async def start(self) -> None:
        logger.info("ddw_clinical_asr started")

    async def stop(self) -> None:
        logger.info("ddw_clinical_asr stopped")

    def setup(self) -> None:
        self._router = router
        if self.app is not None and hasattr(self.app, "include_router"):
            self.app.include_router(router)
