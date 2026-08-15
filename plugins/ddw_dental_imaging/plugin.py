from sdk.plugin_base import PluginBase

from .router import router, set_store
from .store import ImageStore


class Plugin(PluginBase):
    name = "ddw_dental_imaging"
    version = "0.1.0"
    description = "口腔影像管理"
    def __init__(self, app=None, config=None, manifest=None, **kwargs):
        super().__init__(app, config)
        self._store = None
    async def initialize(self):
        from pathlib import Path
        d = Path(__file__).parent / "data"
        img_dir = Path(__file__).parent / "images"
        d.mkdir(parents=True, exist_ok=True)
        img_dir.mkdir(parents=True, exist_ok=True)
        self._store = ImageStore(db_path=d / "imaging.db", root_dir=img_dir)
        set_store(self._store)
    async def start(self): pass
    async def stop(self): pass
    def setup(self):
        self._router = router
        if self.app is not None and hasattr(self.app, "include_router"):
            self.app.include_router(router)
