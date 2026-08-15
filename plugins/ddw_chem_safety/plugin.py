"""DDW 插件主类"""

from .api import router
from . import storage


class PluginBase:
    """插件基类占位（DDW 框架接口）"""
    pass


class Plugin(PluginBase):
    """化工安全合规助手插件"""

    def __init__(self, app, config, manifest=None, **kwargs):
        self.app = app
        self.config = config
        self.manifest = manifest
        self.kwargs = kwargs

        # 初始化数据库
        storage.init_db()

        # 注册路由
        app.include_router(router)

    def get_name(self) -> str:
        from . import PLUGIN_NAME
        return PLUGIN_NAME

    def get_version(self) -> str:
        from . import VERSION
        return VERSION
