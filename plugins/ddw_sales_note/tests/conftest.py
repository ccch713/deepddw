from __future__ import annotations

"""ddw_sales_note 测试 conftest：注入 in-memory SQLite + 种子数据。

注意：本插件依赖 ``crm_companies`` / ``crm_contacts`` / ``crm_opportunities`` 外键表，
全部由 P0-1/P0-2/P0-3 插件提供；conftest 主动 import 这些 models 触发建表。
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


@pytest_asyncio.fixture
async def engine():
    """SQLite 内存数据库引擎（启用 FK 约束，支撑 SET NULL 行为）。"""
    from sqlalchemy import event

    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite 默认不强制 FK，启用 PRAGMA 让 ON DELETE SET NULL 生效
    @event.listens_for(eng.sync_engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    """构造 sessionmaker，并建表。"""
    from core.database import models  # noqa: F401  触发核心模型注册
    from core.database.session import Base
    from plugins.ddw_company_profile import models as cp_models  # noqa: F401
    from plugins.ddw_contact_hub import models as contact_models  # noqa: F401
    from plugins.ddw_opportunity import models as opp_models  # noqa: F401
    from plugins.ddw_sales_note import models as plugin_models  # noqa: F401

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
async def seeded_related(session_factory):
    """为外键引用准备 Company/Contact/Opportunity 占位行。

    返回 dict 含 company_id=100, contact_id=200, opportunity_id=300。
    """
    from plugins.ddw_company_profile.models import Company
    from plugins.ddw_contact_hub.models import Contact
    from plugins.ddw_opportunity.models import Opportunity

    async with session_factory() as s:
        s.add(
            Company(
                id=100,
                tenant_id=1,
                name="测试客户公司",
                status="active",
                certification_status="pending",
                tags=[],
            )
        )
        s.add(Contact(id=200, tenant_id=1, name="测试联系人", status="active"))
        s.add(
            Opportunity(
                id=300,
                tenant_id=1,
                name="测试商机",
                company_id=100,
                status="open",
            )
        )
        await s.commit()
    return {"company_id": 100, "contact_id": 200, "opportunity_id": 300}


# 便捷：直接构造 SalesNoteService（用于单元测试）
@pytest_asyncio.fixture
async def service(seeded_db):
    from plugins.ddw_sales_note.services import SalesNoteService

    return SalesNoteService(seeded_db)


@pytest_asyncio.fixture
async def service_with_related(seeded_db, seeded_related):
    """同 service，但外键引用（company/contact/opportunity）已就位。"""
    from plugins.ddw_sales_note.services import SalesNoteService

    return SalesNoteService(seeded_db)
