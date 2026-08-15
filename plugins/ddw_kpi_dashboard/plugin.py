from sdk.plugin_base import PluginBase

from .router import router, set_db_path


class Plugin(PluginBase):
    name = "ddw_kpi_dashboard"
    version = "0.1.0"
    description = "KPI 与经营报表"
    def __init__(self, app=None, config=None, manifest=None, **kwargs):
        super().__init__(app, config)
    async def initialize(self):
        from pathlib import Path
        d = Path(__file__).parent / "data"
        d.mkdir(parents=True, exist_ok=True)
        set_db_path(d / "kpi_dashboard.db")
    async def start(self): pass
    async def stop(self): pass
    def setup(self):
        self._router = router
        if self.app is not None and hasattr(self.app, "include_router"):
            self.app.include_router(router)
