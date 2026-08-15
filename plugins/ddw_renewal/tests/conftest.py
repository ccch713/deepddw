from __future__ import annotations

"""ddw_renewal 测试 conftest：注入 in-memory SQLite + 种子租户。

本插件是跨插件聚合查询插件，**不创建新表**，但 conftest 必须显式 import
以下插件的 ``models``，让它们注册到 ``Base.metadata``，否则
``Base.metadata.create_all`` 不会建立以下表：

- ``crm_companies``        —— P0-1 ddw_company_profile
- ``crm_licenses``         —— P4-2 ddw_license_core
- ``crm_contracts``        —— P2  ddw_contract_core
"""

import sys
from collections.abc import AsyncIterator
from datetime import datetime, timezone
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


# ---------------------------------------------------------------------------
# 模块级工具
# ---------------------------------------------------------------------------


def _today_utc_naive():
    """naive UTC date（与 license_core / contract_core 一致）。"""
    return datetime.now(timezone.utc).date()


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
    """构造 sessionmaker，并建表（含 3 个依赖插件的模型）。"""
    from core.database import models  # noqa: F401  触发核心模型注册
    from core.database.session import Base
    from plugins.ddw_company_profile import models as cp_models  # noqa: F401
    from plugins.ddw_contact_hub import models as contact_models  # noqa: F401
    from plugins.ddw_contract_core import models as ct_models  # noqa: F401
    from plugins.ddw_license_core import models as lc_models  # noqa: F401
    from plugins.ddw_opportunity import models as opp_models  # noqa: F401
    from plugins.ddw_quotation import models as qt_models  # noqa: F401

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
    """直接构造 RenewalService（用于单元测试）。"""
    from plugins.ddw_renewal.services import RenewalService

    return RenewalService(seeded_db)


@pytest_asyncio.fixture
async def seeded_company(session_factory, seeded_tenant):
    """插入 1 个 company（id=100）并返回 company_id。"""
    from plugins.ddw_company_profile.models import Company

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
        await s.commit()
    return 100


@pytest_asyncio.fixture
async def service_with_company_and_contract(
    seeded_db, seeded_company
):
    """测试 quote 用的 fixture：返回 (db_session, license_id)。

    提前造好：
    - 1 个 company（id=100, name="测试客户公司"）
    - 1 张历史合同：total=36500 CNY, 365 天 → 单价 100 CNY/天
    - 1 个 license：valid_from=今天-365, valid_to=今天, formal, active
    """
    from datetime import timedelta
    from decimal import Decimal

    from plugins.ddw_contract_core.models import Contract
    from plugins.ddw_license_core.models import License

    db = seeded_db
    today = _today_utc_naive()

    # 历史合同
    db.add(
        Contract(
            tenant_id=1,
            company_id=100,
            contract_no="CT-HIST-001",
            title="历史合同",
            contract_type="standard",
            total_amount=Decimal(36500),
            currency="CNY",
            effective_from=today - timedelta(days=365),
            effective_to=today,
            status="active",
        )
    )
    # license：valid_to - valid_from = 365 天
    lic = License(
        tenant_id=1,
        company_id=100,
        license_no="LIC-QUOTE-001",
        license_type="formal",
        plugin_entitlements=["ddw-crm-core"],
        max_users=10,
        max_nodes=1,
        valid_from=today - timedelta(days=365),
        valid_to=today,
        status="active",
    )
    db.add(lic)
    await db.commit()
    await db.refresh(lic)
    return db, lic.id
