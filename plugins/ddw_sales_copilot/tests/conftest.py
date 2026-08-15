from __future__ import annotations

"""ddw_sales_copilot 测试 conftest：注入 in-memory SQLite + 种子租户 + 关联表。

本插件是 AI 能力聚合插件，**不创建新表**，但 conftest 必须显式 import
P0-1~P0-4 / P3-1~P3-2 的 ``models``，让它们注册到 ``Base.metadata``，
否则后续 ``Base.metadata.create_all`` 不会建立 crm_companies /
crm_contacts / crm_opportunities / crm_quotations / crm_sales_notes
等表，跨插件查询会失败。
"""

import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

# 把项目根加入 sys.path
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@pytest_asyncio.fixture
async def engine():
    """SQLite 内存数据库引擎（启用 FK 约束）。"""
    from sqlalchemy import event

    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(eng.sync_engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    """构造 sessionmaker，并建表（含 5 个依赖插件的模型）。"""
    from core.database import models  # noqa: F401  触发核心模型注册
    from core.database.session import Base
    from plugins.ddw_company_profile import models as cp_models  # noqa: F401
    from plugins.ddw_contact_hub import models as contact_models  # noqa: F401
    from plugins.ddw_opportunity import models as opp_models  # noqa: F401
    from plugins.ddw_quotation import models as q_models  # noqa: F401
    from plugins.ddw_sales_note import models as note_models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    return async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncIterator[AsyncSession]:
    """干净的 session（无种子 tenant）。"""
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def seeded_tenant(session_factory):
    """插入 tenant=1，返回 tenant_id。"""
    from core.database.models import Tenant

    async with session_factory() as s:
        s.add(Tenant(id=1, name="测试客户企业", plan="pro", status="active"))
        await s.commit()
    return 1


@pytest_asyncio.fixture
async def seeded_db(session_factory, seeded_tenant) -> AsyncIterator[AsyncSession]:
    """带种子租户的 session。"""
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def service(seeded_db):
    """直接构造 CopilotService（用于单元测试）。"""
    from plugins.ddw_sales_copilot.services import CopilotService

    return CopilotService(seeded_db)


@pytest_asyncio.fixture
async def client() -> AsyncIterator:
    """FastAPI TestClient（异步）：挂载本插件 router。

    配合 ``seeded_db`` 共享同一 engine：seeded_db 写入的数据在 router
    的 session_scope() 中可见（因为都用 StaticPool + 同一内存 SQLite）。
    """
    import httpx
    from fastapi import FastAPI

    from plugins.ddw_sales_copilot.router import build_router

    app = FastAPI(title="ddw-sales-copilot-test")
    app.include_router(build_router())

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
