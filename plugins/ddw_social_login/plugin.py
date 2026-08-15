"""PluginBase 子类 —— 注册路由。"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter

logger = logging.getLogger(__name__)

# 插件元信息
VERSION = "1.0.0"
PLUGIN_NAME = "ddw-social-login"


class Plugin:
    """DDW 社会化登录插件。

    遵循 DDW PluginBase 模式：在 setup() 中构建 router 并注册到 app。
    """

    name: str = PLUGIN_NAME
    version: str = VERSION
    router_prefix: str = "/api/v1/plugins/ddw-social-login"

    def __init__(self, app: Any = None, config: Optional[Dict[str, Any]] = None, manifest: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
        self.app = app
        self.config = dict(config or {})
        self.manifest = dict(manifest or {})
        self._router: Optional[APIRouter] = None
        self._config_manager = None

        # PluginBase.__init__ 自动调 self.setup()
        # setup() 依赖的属性必须在 super().__init__() 之前初始化
        if app is not None:
            self.setup()

    def setup(self) -> None:
        """构建路由并注册到 FastAPI app。"""
        from .config_manager import ConfigManager
        from .router import build_router

        self._config_manager = ConfigManager(self.config)
        self._router = build_router(self._config_manager)

        if self.app is not None:
            self.app.include_router(self._router)
            logger.info("ddw-social-login 插件路由已注册: %s", self.router_prefix)

    async def initialize(self) -> None:
        """异步初始化（可选）。"""
        logger.info("ddw-social-login 插件已初始化")

    async def start(self) -> None:
        """插件启动。"""
        logger.info("ddw-social-login 插件已启动")

    async def stop(self) -> None:
        """插件停止。"""
        logger.info("ddw-social-login 插件已停止")

    async def health(self) -> Dict[str, Any]:
        """健康检查。"""
        return {"status": "ok", "plugin": PLUGIN_NAME, "version": VERSION}
