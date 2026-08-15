from sdk.plugin_base import PluginBase

from .router import router, set_store
from .store import MemberStore


class Plugin(PluginBase):
    name = "ddw_member_vip"
    version = "0.1.0"
    description = "会员储值与等级管理"
    def __init__(self, app=None, config=None, manifest=None, **kwargs):
        super().__init__(app, config)
        self._store = None
    async def initialize(self):
        from pathlib import Path
        d = Path(__file__).parent / "data"
        d.mkdir(parents=True, exist_ok=True)
        self._store = MemberStore(db_path=d / "member_vip.db")
        set_store(self._store)
    async def start(self): pass
    async def stop(self): pass
    def setup(self):
        self._router = router
        if self.app is not None and hasattr(self.app, "include_router"):
            self.app.include_router(router)
