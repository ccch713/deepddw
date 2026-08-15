from __future__ import annotations

"""ddw_voice_capture 测试 conftest：注入 in-memory SQLite + 种子租户 + 关联表占位。

本插件外键引用：
- crm_companies（ddw_company_profile 提供）
- crm_contacts（ddw_contact_hub 提供）
- crm_opportunities（ddw_opportunity 提供）

跨插件回归时由真实插件模型注册到 metadata；单插件测试时使用真实 Company/Contact/
Opportunity 模型直接插入种子行，验证 ON DELETE SET NULL 行为。
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
    """SQLite 内存数据库引擎（启用 FK 约束以验证 ON DELETE SET NULL）。"""
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
    """构造 sessionmaker，建表（含核心模型 + 三个依赖插件 + 本插件模型）。"""
    from core.database import models  # noqa: F401  触发核心模型注册
    from core.database.session import Base
    from plugins.ddw_company_profile import models as cp_models  # noqa: F401
    from plugins.ddw_contact_hub import models as contact_models  # noqa: F401
    from plugins.ddw_opportunity import models as opp_models  # noqa: F401
    from plugins.ddw_voice_capture import models as plugin_models  # noqa: F401

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
async def seeded_associations(session_factory, seeded_tenant):
    """插入 1 个企业 + 1 个联系人 + 1 个商机，返回 (company_id, contact_id, opportunity_id)。

    本插件外键依赖这些表，跨插件回归时由真实模型提供；本测试固定插入种子行。
    """
    from plugins.ddw_company_profile.models import Company
    from plugins.ddw_contact_hub.models import Contact
    from plugins.ddw_opportunity.models import Opportunity

    company_id = 100
    contact_id = 200
    opportunity_id = 300

    async with session_factory() as s:
        s.add(
            Company(
                id=company_id,
                tenant_id=1,
                name="测试客户公司",
                status="active",
                certification_status="pending",
                tags=[],
            )
        )
        s.add(
            Contact(
                id=contact_id,
                tenant_id=1,
                company_id=company_id,
                name="张三",
                status="active",
                tags=[],
                groups=[],
            )
        )
        s.add(
            Opportunity(
                id=opportunity_id,
                tenant_id=1,
                company_id=company_id,
                contact_id=contact_id,
                name="测试商机",
                stage="initial_contact",
                status="open",
                probability=10,
                tags=[],
            )
        )
        await s.commit()
    return company_id, contact_id, opportunity_id


# 便捷：直接构造 VoiceRecordService（用于单元测试）
@pytest_asyncio.fixture
async def service(seeded_db):
    from plugins.ddw_voice_capture.services import VoiceRecordService

    return VoiceRecordService(seeded_db)


@pytest_asyncio.fixture
async def service_with_assoc(seeded_db, seeded_associations):
    """同 service，但 crm_companies/crm_contacts/crm_opportunities 种子行已就位。"""
    from plugins.ddw_voice_capture.services import VoiceRecordService

    return VoiceRecordService(seeded_db)
