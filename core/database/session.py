"""SQLAlchemy 异步 session 工厂 + Declarative Base。

供 ``core/main.py`` lifespan 启动时初始化，所有 ORM Model 共享 ``Base`` 与 ``session_scope()``。
"""

from __future__ import annotations

import asyncio
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


# P0-1（multidevice）：SQLite 并发加固——WAL + busy_timeout + synchronous=NORMAL
# 通过 SQLAlchemy event listener 在每个连接建立时执行 PRAGMA，覆盖 async 引擎
# 的连接池复用；配合 knowledge.py 模块级单连接锁，消除多设备并发写锁冲突。
_SQLITE_PRAGMAS = (
    "PRAGMA journal_mode=WAL;",
    "PRAGMA busy_timeout=5000;",
    "PRAGMA synchronous=NORMAL;",
    "PRAGMA foreign_keys=ON;",
)

# 跨表写事务的全局串行化锁（asyncio）：多设备并发写记忆/知识库时，
# 写路径先获取本锁，避免 interleaved 写事务触发 SQLITE_BUSY。
_write_lock: Optional[asyncio.Lock] = None


def get_write_lock() -> asyncio.Lock:
    """进程级写串行化锁（P0-1）：跨表写事务（记忆+文档索引等）用。"""
    global _write_lock
    if _write_lock is None:
        _write_lock = asyncio.Lock()
    return _write_lock


def _apply_sqlite_pragmas(dbapi_connection, connection_record) -> None:  # noqa: ARG001
    """SQLAlchemy 连接事件：SQLite 连接建立后执行并发加固 PRAGMA。"""
    try:
        cursor = dbapi_connection.cursor()
        for stmt in _SQLITE_PRAGMAS:
            cursor.execute(stmt)
        cursor.close()
    except Exception:  # noqa: BLE001  # PRAGMA 失败不阻断建连（降级）
        logger.warning("sqlite pragma setup degraded", exc_info=True)


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.main_db_url
        connect_args: dict = {}
        if url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
            # P0-1：把 PRAGMA 挂到 connect 事件（连接池每条连接都执行）
            from sqlalchemy import event

            _engine = create_async_engine(
                url,
                echo=settings.databases.get("main", {}).get("echo", False),
                pool_size=settings.databases.get("main", {}).get("pool_size", 5),
                connect_args=connect_args,
            )
            event.listen(_engine.sync_engine, "connect", _apply_sqlite_pragmas)
        else:
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
    """启动时建表。

    deepDDW 单机 SQLite：create_all（幂等，自动补齐新表）+ 兼容表（chat_messages）。
    """
    engine = get_engine()
    async with engine.begin() as conn:
        from core.database import models  # noqa: F401  触发模型注册

        await conn.run_sync(Base.metadata.create_all)
        # chat_messages：Chat API 以 SQLAlchemy Table 直连（兼容旧库），补建表
        from sqlalchemy import text

        await conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                tenant_id INTEGER,
                conversation_id VARCHAR(64),
                role VARCHAR(16),
                content TEXT,
                provider VARCHAR(64),
                model VARCHAR(128),
                tokens_in INTEGER,
                tokens_out INTEGER,
                cost FLOAT,
                created_at DATETIME,
                updated_at DATETIME
            )
            """
        ))
    logger.info("deepDDW DB schema ensured")


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
