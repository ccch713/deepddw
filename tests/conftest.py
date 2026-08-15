"""DDW AI Hub 测试配置。"""

from __future__ import annotations

import asyncio
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# 测试前设置环境
os.environ.setdefault("DDW_JWT_SECRET", "test-secret-key-for-testing-32bytes-ok")

from core.database.session import Base, get_engine, get_session_maker  # noqa: E402
from core.main import app  # noqa: E402




@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """创建测试用 SQLite 内存数据库。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        from core.database import models  # noqa: F401

        # 幂等：全量跑时 session 级 fixture 可能被实例化多次（pytest-asyncio loop scope），
        # drop_all + create_all 保证每次重建干净 schema，避免 "index already exists"
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def client(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """创建测试用 HTTP 客户端。"""
    # 覆盖 session 工厂
    import core.database.session as session_mod

    original_engine = session_mod._engine
    original_maker = session_mod._session_maker

    session_mod._engine = test_engine
    session_mod._session_maker = async_sessionmaker(
        bind=test_engine, expire_on_commit=False, class_=AsyncSession
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    session_mod._engine = original_engine
    session_mod._session_maker = original_maker


# ---------------------------------------------------------------------------
# 列表端点契约校验 helper
# ---------------------------------------------------------------------------


def assert_list_response(resp):
    """列表端点契约校验：必须 {items, total}"""
    assert resp.status_code < 400, f"请求失败: {resp.status_code}"
    data = resp.json()
    assert "items" in data, f"列表端点缺少 items 字段: {list(data.keys())}"
    assert "total" in data, "列表端点缺少 total 字段"
    assert isinstance(data["items"], list), "items 必须是数组"
    assert data["total"] == len(data["items"]), "total 必须等于 items 长度"
