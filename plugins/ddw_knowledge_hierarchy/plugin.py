"""DDW Knowledge Hierarchy — Plugin 入口（2026-08-08 完成 router 接入 services）.

生命周期：
- initialize(): 创建独立 Base 表（kh_* 表，平台 Base 不含）+ 注入 vector store 路径
- setup(): 注册 FastAPI router
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    name = "ddw_knowledge_hierarchy"
    version = "1.0.0"
    description = "企业级层级知识检索引擎"
    router_prefix = "/api/v1/plugins/ddw-knowledge-hierarchy"

    def __init__(self, app: Any = None, config: Optional[dict] = None, manifest: Any = None, **kwargs) -> None:
        super().__init__(app, config)
        self._data_dir: Optional[Path] = None

    async def initialize(self) -> None:
        """建表 + 准备数据目录。"""
        from core.database.session import get_engine

        from .models import Base

        # 独立 Base 的表需要插件自己 create_all（平台 init_db 只建平台 Base）
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("ddw_knowledge_hierarchy: kh_* tables ensured")

        # 数据目录（向量库）
        self._data_dir = Path(__file__).resolve().parent / "data"
        self._data_dir.mkdir(parents=True, exist_ok=True)

        # 注入向量库路径到 router
        from .router import set_vector_store_path

        set_vector_store_path(self._data_dir / "kh_vector.db")
        logger.info("ddw_knowledge_hierarchy initialized: data=%s", self._data_dir)

    async def start(self) -> None:
        if self._data_dir is None:
            await self.initialize()
        logger.info("ddw_knowledge_hierarchy started")

    async def stop(self) -> None:
        logger.info("ddw_knowledge_hierarchy stopped")

    def setup(self) -> None:
        """注册 FastAPI router（兼容新旧 SDK，统一挂 /api/v1/plugins/ddw-knowledge-hierarchy）。"""
        # 独立 Base 的表需要插件自己建（load_plugins 只调 register，不调 initialize）
        self._ensure_tables()

        from fastapi import APIRouter

        from .distill_router import router as distill_router
        from .kb_router import router as kb_router
        from .router import router as kh_router

        if hasattr(self, "router"):
            # 新版 SDK：self.router 已带 prefix，include_router 会拼接 prefix
            self.router.include_router(kh_router)
            self.router.include_router(kb_router)
            self.router.include_router(distill_router)
            self._router = self.router
        else:
            # 旧版 SDK：构造带 prefix 的 router（必须用 include_router，
            # 手动 extend routes 会绕过 prefix 拼接）
            prefixed = APIRouter(prefix="/api/v1/plugins/ddw-knowledge-hierarchy")
            prefixed.include_router(kh_router)
            prefixed.include_router(kb_router)
            prefixed.include_router(distill_router)
            self._router = prefixed
        # 不在此 include——由 SDK register() 统一挂载（避免重复注册）
        logger.info("ddw_knowledge_hierarchy v%s registered", self.version)

    @staticmethod
    def _ensure_tables() -> None:
        """同步建 kh_* 表（平台主 DB 为 SQLite；与 async engine 同文件）。"""

        from sqlalchemy import create_engine

        from core.config import get_settings

        from .models import Base

        try:
            cfg = get_settings().databases.get("main", {})
            db_path = cfg.get("path", "./data/ddw_main.db")
            sync_engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(sync_engine)
            sync_engine.dispose()
            logger.info("ddw_knowledge_hierarchy: kh_* tables ensured (%s)", db_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ddw_knowledge_hierarchy: table ensure failed: %s", exc)


__all__ = ["Plugin"]
