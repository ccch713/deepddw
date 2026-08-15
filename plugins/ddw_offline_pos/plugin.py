"""DDW Payment - Plugin."""
from __future__ import annotations

import logging
from typing import Any, Optional

from sdk.plugin_base import PluginBase

from .router import router, set_store
from .store import PaymentStore

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    name = "ddw_offline_pos"
    version = "0.1.0"
    description = "收费与支付管理"

    def __init__(self, app: Any = None, config: Optional[dict] = None, manifest: Any = None, **kwargs) -> None:
        super().__init__(app, config)
        self._store: Optional[PaymentStore] = None

    async def initialize(self) -> None:
        from pathlib import Path
        data_dir = Path(__file__).parent / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        self._store = PaymentStore(db_path=data_dir / "payment.db")
        set_store(self._store)
        logger.info("ddw_offline_pos initialized")

    async def start(self) -> None:
        logger.info("ddw_offline_pos started")

    async def stop(self) -> None:
        logger.info("ddw_offline_pos stopped")

    def setup(self) -> None:
        self._router = router
        if self.app is not None and hasattr(self.app, "include_router"):
            self.app.include_router(router)
