from __future__ import annotations

"""ddw_contract_core 测试 conftest：注入 in-memory SQLite + 种子租户 + 占位外键表。"""

import sys
from decimal import Decimal
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
    """SQLite 内存数据库引擎（启用 FK 约束，支撑 CASCADE 行为）。"""
    from sqlalchemy import event

    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite 默认不强制 FK，导致 ON DELETE SET NULL / CASCADE 不生效
    # 通过事件钩子在每个新连接上发出 PRAGMA foreign_keys=ON
    @event.listens_for(eng.sync_engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    """构造 sessionmaker，并建表（含核心模型 + 本插件模型 + 缺失的关联表占位）。

    本插件 Contract 表同时引用 4 张外键表（crm_companies / crm_contacts /
    crm_opportunities / crm_quotations），全部使用 use_alter=True 的 FK 声明。
    真实生产环境由 P0-1~P0-4 插件提供，独立测试时需要占位表让 metadata
    resolve_fks() 能成功。
    """
    from sqlalchemy import Column, Integer, Table

    from core.database import models  # noqa: F401  触发核心模型注册
    from core.database.session import Base
    from plugins.ddw_contract_core import models as plugin_models  # noqa: F401

    for tbl_name in (
        "crm_companies",
        "crm_contacts",
        "crm_opportunities",
        "crm_quotations",
    ):
        if tbl_name not in Base.metadata.tables:
            Table(
                tbl_name,
                Base.metadata,
                Column("id", Integer, primary_key=True, autoincrement=True),
            )

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
    """为外键引用准备占位/真实记录。

    Contract 引用 4 张表：crm_companies / crm_contacts / crm_opportunities /
    crm_quotations。本插件没有明细依赖，测试中不强求真实字段值，仅需要
    存在对应 id 让外键满足。
    """
    from sqlalchemy import insert

    from core.database.session import Base

    async with session_factory() as s:
        # crm_companies：尝试用真实 Company（如果加载了 ddw_company_profile），否则 stub
        companies_tbl = Base.metadata.tables["crm_companies"]
        if "name" in companies_tbl.c:
            try:
                from plugins.ddw_company_profile.models import Company

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
            except ImportError:
                await s.execute(
                    insert(companies_tbl).values(
                        id=100, name="测试客户公司", status="active"
                    )
                )
        else:
            await s.execute(insert(companies_tbl).values(id=100))

        # crm_contacts
        contacts_tbl = Base.metadata.tables["crm_contacts"]
        if "name" in contacts_tbl.c:
            try:
                from plugins.ddw_contact_hub.models import Contact

                s.add(Contact(id=200, tenant_id=1, name="测试联系人", status="active"))
            except (ImportError, Exception):  # noqa: BLE001
                try:
                    await s.execute(
                        insert(contacts_tbl).values(
                            id=200, name="测试联系人", status="active"
                        )
                    )
                except Exception:  # noqa: BLE001
                    await s.execute(insert(contacts_tbl).values(id=200, name="测试联系人"))
        else:
            await s.execute(insert(contacts_tbl).values(id=200))

        # crm_opportunities
        opps_tbl = Base.metadata.tables["crm_opportunities"]
        if "name" in opps_tbl.c:
            try:
                from plugins.ddw_opportunity.models import Opportunity

                s.add(
                    Opportunity(
                        id=300,
                        tenant_id=1,
                        name="测试商机",
                        company_id=100,
                        status="open",
                    )
                )
            except (ImportError, Exception):  # noqa: BLE001
                try:
                    await s.execute(
                        insert(opps_tbl).values(
                            id=300, name="测试商机", company_id=100, status="open"
                        )
                    )
                except Exception:  # noqa: BLE001
                    await s.execute(insert(opps_tbl).values(id=300, name="测试商机"))
        else:
            await s.execute(insert(opps_tbl).values(id=300))

        # crm_quotations（Contract 唯一新增的 FK 目标）
        # 优先用真实 Quotation（如果加载了 ddw_quotation），否则用 stub。
        # 注意：真实 Quotation 创建需 items 列表，独立测试只插占位行。
        quotations_tbl = Base.metadata.tables["crm_quotations"]
        if "quotation_no" in quotations_tbl.c:
            try:
                from plugins.ddw_quotation.models import Quotation

                s.add(
                    Quotation(
                        id=400,
                        tenant_id=1,
                        quotation_no="QT-TEST-001",
                        currency="CNY",
                        discount_rate=Decimal("100"),
                    )
                )
            except (ImportError, Exception):  # noqa: BLE001
                try:
                    await s.execute(
                        insert(quotations_tbl).values(
                            id=400,
                            tenant_id=1,
                            quotation_no="QT-TEST-001",
                            currency="CNY",
                        )
                    )
                except Exception:  # noqa: BLE001
                    await s.execute(
                        insert(quotations_tbl).values(
                            id=400, quotation_no="QT-TEST-001"
                        )
                    )
        else:
            await s.execute(insert(quotations_tbl).values(id=400))

        await s.commit()
    return {
        "company_id": 100,
        "contact_id": 200,
        "opportunity_id": 300,
        "quotation_id": 400,
    }


# 便捷：直接构造 ContractService（用于单元测试）
@pytest_asyncio.fixture
async def service(seeded_db):
    from plugins.ddw_contract_core.services import ContractService

    return ContractService(seeded_db)


@pytest_asyncio.fixture
async def service_with_related(seeded_db, seeded_related):
    """同 service，但外键引用（company/contact/opportunity/quotation）已就位。"""
    from plugins.ddw_contract_core.services import ContractService

    return ContractService(seeded_db)
