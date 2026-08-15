from __future__ import annotations

"""ddw_opportunity 测试 conftest：注入 in-memory SQLite + 种子数据。

注意：本插件依赖 ``crm_companies`` / ``crm_contacts`` 外键表。
- ``crm_companies`` 由 ddw_company_profile 插件提供（直接 import models 触发建表）。
- ``crm_contacts`` 在 P0-3 时尚无插件提供，因此 conftest 临时注册一个 stub
  Contact 表，仅用于让 SQLAlchemy ``create_all`` 通过（无任何实际数据）。
"""

import sys
from pathlib import Path
from typing import AsyncIterator

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


def _register_stub_contact_table() -> None:
    """注册一个空的 ``crm_contacts`` stub 表，仅用于让 FK 元数据完整。

    真实联系人表由后续 P 序插件提供；P0-3 测试只需 ``crm_opportunities`` 能 create。
    直接用 ``Table`` 元数据对象，避免在 conftest 里写一个完整的 ORM 类。
    """
    from sqlalchemy import BigInteger, Column, Integer, String, Table

    from core.database.session import Base

    if "crm_contacts" in Base.metadata.tables:
        return

    BigInt = BigInteger().with_variant(Integer(), "sqlite")
    Table(
        "crm_contacts",
        Base.metadata,
        Column("id", BigInt, primary_key=True, autoincrement=True),
        Column("tenant_id", BigInt, nullable=False, index=True),
        Column("name", String(100), nullable=False, server_default=""),
    )


@pytest_asyncio.fixture
async def engine():
    """SQLite 内存数据库引擎。"""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    """构造 sessionmaker，并建表。"""
    from core.database import models  # noqa: F401  触发核心模型注册
    from core.database.session import Base
    from plugins.ddw_company_profile import models as cp_models  # noqa: F401
    from plugins.ddw_opportunity import models as opp_models  # noqa: F401

    _register_stub_contact_table()

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


# 便捷：直接构造 OpportunityService（用于单元测试）
@pytest_asyncio.fixture
async def service(seeded_db):
    from plugins.ddw_opportunity.services import OpportunityService

    return OpportunityService(seeded_db)
