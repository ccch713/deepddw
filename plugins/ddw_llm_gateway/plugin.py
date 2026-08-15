from typing import Any, Optional

class PluginBase:
    """模拟 PluginBase 基类，实际应从 ddw_core.plugin_base 导入"""
    def __init__(self, app: Any, config: dict, manifest: Optional[dict] = None, **kwargs):  # noqa: E501
        self.app = app
        self.config = config
        self.manifest = manifest or {}
        self._router = None

    def setup(self):
        """初始化插件，注册路由"""
        raise NotImplementedError

class Plugin(PluginBase):
    """DDW LLM Gateway 插件"""

    def __init__(self, app: Any, config: dict, manifest: Optional[dict] = None, **kwargs):  # noqa: E501
        super().__init__(app, config, manifest, **kwargs)
        self._router = None

    def setup(self):
        """初始化插件，注册路由"""
        try:
            from .router import router, set_storage
            from .storage import Storage
        except ImportError:
            from router import router, set_storage
            from storage import Storage
        self._router = router
        self.app.include_router(router)
        # 初始化存储等
        self.storage = Storage()
        self.storage.init_db()
        set_storage(self.storage)
