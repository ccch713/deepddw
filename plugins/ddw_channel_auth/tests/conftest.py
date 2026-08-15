"""DDW 渠道授权与结算插件测试 fixtures。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.database.models import Base


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def db_engine():
    """SQLite 内存数据库引擎。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """异步数据库 session（直连测试引擎）。"""
    session_maker = async_sessionmaker(
        bind=db_engine, expire_on_commit=False, class_=AsyncSession
    )
    async with session_maker() as session:
        yield session


@pytest.fixture
async def client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    """HTTP 测试客户端（mock session_scope 以使用测试数据库）。"""
    from plugins.ddw_channel_auth import router as router_mod

    session_maker = async_sessionmaker(
        bind=db_engine, expire_on_commit=False, class_=AsyncSession
    )

    @asynccontextmanager
    async def _mock_session_scope():
        async with session_maker() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    # 替换模块级 session_scope 引用
    original = router_mod.session_scope
    router_mod.session_scope = _mock_session_scope

    from fastapi import FastAPI
    from plugins.ddw_channel_auth.router import build_router

    app = FastAPI()
    # router 已内置 prefix，include_router 不再重复
    app.include_router(build_router())

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    # 恢复原始引用
    router_mod.session_scope = original
