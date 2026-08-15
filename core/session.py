"""SQLAlchemy 异步 session 工厂 + Declarative Base。

供 ``core/main.py`` lifespan 启动时初始化，所有 ORM Model 共享 ``Base`` 与 ``session_scope()``。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from core.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """所有 ORM 模型的根。"""


_engine: Optional[AsyncEngine] = None
_session_maker: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.main_db_url
        connect_args: dict = {}
        if url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
        _engine = create_async_engine(
            url,
            echo=settings.databases.get("main", {}).get("echo", False),
            pool_size=settings.databases.get("main", {}).get("pool_size", 5),
            connect_args=connect_args,
        )
        logger.info("DDW async engine created: %s", url)
    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    global _session_maker
    if _session_maker is None:
        _session_maker = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_maker


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """异步上下文管理器：每次请求一个 session，异常自动 rollback。"""
    async with get_session_maker()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """启动时建表（仅 dev 用，生产用 Alembic）。"""
    engine = get_engine()
    async with engine.begin() as conn:
        from core.database import models  # noqa: F401  触发模型注册

        await conn.run_sync(Base.metadata.create_all)
    logger.info("DDW DB schema ensured")


async def dispose_db() -> None:
    global _engine, _session_maker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_maker = None
        logger.info("DDW async engine disposed")


__all__ = [
    "Base",
    "dispose_db",
    "get_engine",
    "get_session_maker",
    "init_db",
    "session_scope",
]
