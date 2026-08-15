"""DDW LLM 用量中枢 — 插件入口（Plugin 类）。

适配本地底座 SDK v1 协议（``sdk/plugin_base.PluginBase``）：
    * ``__init__`` 接收 ``(app, config=None, manifest=None, **kwargs)``；
    * 父类 ``__init__`` 已经创建 ``self.router``（带 prefix 的空 APIRouter），
      并在末尾自动调一次 ``self.setup()``，所以子类 ``setup()`` 只做
      「往 self.router 加路由」这一件事；
    * 父类 ``register()`` 会 ``self.app.include_router(self.router)``，
      所以子类不需要再手动 include；
    * ``__init__`` 显式声明 ``**kwargs`` 兜底，防止底座未来加新参数直接爆。

数据库文件落 ``data/llm_usage.db``（相对插件目录，自动创建）。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from sdk.plugin_base import PluginBase

from . import PLUGIN_NAME, VERSION
from .api import register_routes
from .storage import UsageStorage

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """ddw_llm_usage 插件主类。"""

    def __init__(
        self,
        app: Any = None,
        config: Optional[dict] = None,
        manifest: Optional[dict] = None,
        **kwargs: Any,
    ) -> None:
        # 在父类 __init__ 之前先设好 name/version，
        # 让父类创建的 self.router 用正确的 prefix。
        self.name: str = PLUGIN_NAME
        self.version: str = VERSION
        self.router_prefix: str = f"/api/v1/plugins/{PLUGIN_NAME}"
        super().__init__(app=app, config=config, manifest=manifest)
        # 适配开发仓 SDK v2 PluginBase：父类不自动创建 self.router /
        # 不自动调 setup()。这里补齐 router 并立即 setup（幂等 guard），
        # register()（v2 兼容）会 include_router(self.router)。
        from fastapi import APIRouter

        self.router = APIRouter(prefix=self.router_prefix, tags=[PLUGIN_NAME])
        self.setup()

    def setup(self) -> None:
        """底座在 ``__init__`` 末尾自动调一次。

        职责：
            1. 解析 db_path 并初始化 storage（写入 self.storage）；
            2. 把所有路由挂到父类创建的 ``self.router`` 上。

        注意：不在这里 ``include_router``，留给底座的 ``register()`` 统一挂载。
        SDK v1 父类 ``register()`` 实现是 ``self.app.include_router(self.router)``，
        此时 ``self.router`` 已包含所有 routes。
        """
        # 1) 解析 db_path：manifest.config.db_path > self.config.get > 默认
        manifest_cfg = (self.manifest or {}).get("config", {}) or {}
        db_path_raw = str(
            manifest_cfg.get("db_path")
            or (self.config.get("db_path") if self.config is not None else None)
            or "data/llm_usage.db"
        )
        db_path = Path(db_path_raw)
        if not db_path.is_absolute():
            db_path = (Path(__file__).resolve().parent / db_path).resolve()

        # 安全校验：相对路径不能含 ..（防路径遍历），且必须位于插件目录 data/ 子目录下
        if not Path(db_path_raw).is_absolute():
            if ".." in db_path_raw:
                raise ValueError(f"db_path must not contain '..': {db_path_raw}")
            allowed_dir = (Path(__file__).resolve().parent / "data").resolve()
            if not str(db_path).startswith(str(allowed_dir) + os.sep) and db_path != allowed_dir:  # noqa: E501
                raise ValueError(f"db_path must be under {allowed_dir}, got: {db_path}")

        self.storage = UsageStorage(db_path)
        self.db_path = db_path

        # 2) 把所有路由挂到 self.router（父类创建好 prefix 的那个）
        #    用 guard 防重复挂载（__init__ 已调过 setup()，如果测试再调一次会双加）
        if not getattr(self, "_routes_registered", False):
            register_routes(self.router, self)
            self._routes_registered = True

        logger.debug(
            "ddw_llm_usage %s setup done (db=%s, prefix=%s)",
            self.version,
            db_path,
            self.router_prefix,
        )


__all__ = ["Plugin"]
