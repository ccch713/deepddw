"""DDW Dental EMR - Plugin 入口."""
from __future__ import annotations

import logging
from typing import Any, Optional

from sdk.plugin_base import PluginBase

from .router import router, set_data_dir, set_store
from .store import DentalRecordStore

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    name = "ddw_dental_emr"
    version = "0.1.0"
    description = "口腔病历主插件（基于 9 类模板）"

    def __init__(self, app: Any = None, config: Optional[dict] = None, manifest: Any = None, **kwargs) -> None:
        super().__init__(app, config)
        self._store: Optional[DentalRecordStore] = None
        self._router = None

    async def initialize(self) -> None:
        from pathlib import Path

        from . import __init__ as pkg_init  # noqa: F401

        data_dir = Path(__file__).parent / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        set_data_dir(data_dir)
        self._store = DentalRecordStore(db_path=data_dir / "dental_emr.db")
        set_store(self._store)
        logger.info("ddw_dental_emr initialized: db=%s", data_dir / "dental_emr.db")

    async def start(self) -> None:
        logger.info("ddw_dental_emr started")

    async def stop(self) -> None:
        logger.info("ddw_dental_emr stopped")

    def setup(self) -> None:
        self._router = router
        if self.app is not None and hasattr(self.app, "include_router"):
            self.app.include_router(router)
