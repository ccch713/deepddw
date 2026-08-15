"""DDW Commission - Plugin."""
from __future__ import annotations

from typing import Any, Optional

from sdk.plugin_base import PluginBase

from .router import router, set_store
from .store import CommissionStore


class Plugin(PluginBase):
    name = "ddw_commission"
    version = "0.1.0"
    description = "医生提成核算（基于 T5 收费数据）"

    def __init__(self, app: Any = None, config: Optional[dict] = None, manifest: Any = None, **kwargs) -> None:
        super().__init__(app, config)
        self._store: Optional[CommissionStore] = None

    async def initialize(self) -> None:
        from pathlib import Path
        data_dir = Path(__file__).parent / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        self._store = CommissionStore(db_path=data_dir / "commission.db")
        set_store(self._store)

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    def setup(self) -> None:
        self._router = router
        if self.app is not None and hasattr(self.app, "include_router"):
            self.app.include_router(router)
