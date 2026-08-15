from __future__ import annotations

"""ddw_signature_adapter 测试 conftest：注入 in-memory SQLite + 种子租户 + 合同。

crm_signature_requests 表的外键依赖：
- crm_contracts  由 ddw_contract_core (P2-3) 提供

测试策略：conftest 主动 import P2-3 真实模型触发建表（与 license_core 相同模式）。
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
    from plugins.ddw_company_profile import models as company_models  # noqa: F401
    from plugins.ddw_contact_hub import models as contact_models  # noqa: F401
    from plugins.ddw_contract_core import models as contract_models  # noqa: F401
    from plugins.ddw_opportunity import models as opportunity_models  # noqa: F401
    from plugins.ddw_quotation import models as quotation_models  # noqa: F401
    from plugins.ddw_signature_adapter import models as plugin_models  # noqa: F401

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
async def seeded_contract(session_factory, seeded_tenant):
    """插入一个测试 contract（status=draft），返回 contract_id。"""
    from plugins.ddw_contract_core.models import Contract

    async with session_factory() as s:
        s.add(
            Contract(
                id=200,
                tenant_id=1,
                contract_no="CT-20260101-001",
                title="测试合同",
                contract_type="standard",
                currency="CNY",
                version=1,
                status="draft",
            )
        )
        await s.commit()
    return 200


# 便捷：直接构造 SignatureRequestService（用于单元测试）
@pytest_asyncio.fixture
async def service(seeded_db):
    from plugins.ddw_signature_adapter.services import SignatureRequestService

    return SignatureRequestService(seeded_db)


@pytest_asyncio.fixture
async def service_with_contract(seeded_db, seeded_contract):
    """同 service，但 crm_contracts 已就位可用。"""
    from plugins.ddw_signature_adapter.services import SignatureRequestService

    return SignatureRequestService(seeded_db)
