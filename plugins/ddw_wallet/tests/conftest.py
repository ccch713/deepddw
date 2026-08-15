"""ddw_wallet 测试 fixtures — 内存 SQLite + mock 支付客户端。"""
from __future__ import annotations

import asyncio
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from plugins.ddw_wallet.models import WalletBase

# 强制使用内存 SQLite 测试
os.environ["DDW_WALLET_DB_URL"] = "sqlite+aiosqlite://"




@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """创建内存 SQLite 引擎，每个测试函数重建。"""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(WalletBase.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(WalletBase.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def session(
    db_engine,
) -> AsyncGenerator[AsyncSession, None]:
    """每个测试函数一个独立 session。"""
    session_factory = async_sessionmaker(
        bind=db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    async with session_factory() as s:
        yield s
