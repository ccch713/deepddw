from sdk.plugin_base import PluginBase

from .router import router, set_store
from .store import AggregatedPayStore


class Plugin(PluginBase):
    name = "ddw_aggregated_pay"
    version = "0.1.0"
    description = "聚合支付与对账"
    def __init__(self, app=None, config=None, manifest=None, **kwargs):
        super().__init__(app, config)
        self._store = None
    async def initialize(self):
        from pathlib import Path
        d = Path(__file__).parent / "data"
        d.mkdir(parents=True, exist_ok=True)
        self._store = AggregatedPayStore(db_path=d / "aggregated_pay.db")
        set_store(self._store)
    async def start(self): pass
    async def stop(self): pass
    def setup(self):
        self._router = router
        if self.app is not None and hasattr(self.app, "include_router"):
            self.app.include_router(router)
