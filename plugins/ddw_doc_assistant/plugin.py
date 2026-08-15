"""DDW Doc Assistant — Plugin 入口。

生命周期：
- initialize(): 创建独立 da_* 表 + 注入 vector store 路径
- setup(): 注册 FastAPI router（self._router = router, self.app.include_router(router)）
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    name = "ddw_doc_assistant"
    version = "1.0.0"
    description = "设计院/研究院文档知识助手"

    def __init__(self, app: Any = None, config: Optional[dict] = None, manifest: Any = None, **kwargs) -> None:
        super().__init__(app, config)
        self._data_dir: Optional[Path] = None

    async def initialize(self) -> None:
        """建表 + 准备数据目录。"""
        from core.database.session import get_engine

        from .models import Base

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("ddw_doc_assistant: da_* tables ensured")

        self._data_dir = Path(__file__).resolve().parent / "data"
        self._data_dir.mkdir(parents=True, exist_ok=True)

        from .router import set_vector_store_path

        set_vector_store_path(self._data_dir / "da_vector.db")
        logger.info("ddw_doc_assistant initialized: data=%s", self._data_dir)

    async def start(self) -> None:
        if self._data_dir is None:
            await self.initialize()
        logger.info("ddw_doc_assistant started")

    async def stop(self) -> None:
        logger.info("ddw_doc_assistant stopped")

    def setup(self) -> None:
        """注册 FastAPI router。"""
        self._ensure_tables()

        from .router import router as doc_router

        self._router = doc_router
        if self.app is not None and hasattr(self.app, "include_router"):
            self.app.include_router(doc_router)
        logger.info("ddw_doc_assistant v%s registered", self.version)

    @staticmethod
    def _ensure_tables() -> None:
        """同步建 da_* 表。"""
        from sqlalchemy import create_engine

        from core.config import get_settings

        from .models import Base

        try:
            cfg = get_settings().databases.get("main", {})
            db_path = cfg.get("path", "./data/ddw_main.db")
            sync_engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(sync_engine)
            sync_engine.dispose()
            logger.info("ddw_doc_assistant: da_* tables ensured (%s)", db_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ddw_doc_assistant: table ensure failed: %s", exc)


__all__ = ["Plugin"]
