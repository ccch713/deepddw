from __future__ import annotations

"""ddw_quotation 测试 conftest：注入 in-memory SQLite + 种子租户。"""

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
    """SQLite 内存数据库引擎（启用 FK 约束，支撑 CASCADE 行为）。"""
    from sqlalchemy import event

    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite 默认不强制 FK，导致 ON DELETE CASCADE 不生效
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
    """构造 sessionmaker，并建表（含核心模型 + 本插件模型 + 缺失的关联表占位）。"""
    # 本插件的 FK 引用 crm_companies / crm_contacts / crm_opportunities：
    # 真实生产环境由 ddw_company_profile 等插件提供；独立测试时需要占位表
    # 让 metadata.resolve_fks() 能成功。占位表只含 id，零业务字段。
    from sqlalchemy import Column, Integer, Table

    from core.database import models  # noqa: F401  触发核心模型注册
    from core.database.session import Base
    from plugins.ddw_quotation import models as plugin_models  # noqa: F401

    for tbl_name in ("crm_companies", "crm_contacts", "crm_opportunities"):
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
    """为外键引用准备占位/真实记录，返回 dict 含 company_id/contact_id/opportunity_id。

    策略：
    - crm_companies：可能为真实 Company（ddw_company_profile 加载）→ 插入 Company 行；
      否则（独立测试）用 stub（仅 id）。
    - crm_contacts：可能为真实 Contact（ddw_contact_hub 加载）→ 插入 Contact 行；
      否则用 stub。
    - crm_opportunities：可能为真实 Opportunity（ddw_opportunity 加载）→ 插入 Opportunity 行；
      否则用 stub。
    """
    from sqlalchemy import insert

    from core.database.session import Base

    async with session_factory() as s:
        # crm_companies
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
                # 兜底：插入最小行（status 等默认值可能因模型而异）
                try:
                    await s.execute(
                        insert(contacts_tbl).values(id=200, name="测试联系人", status="active")
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

                # 实际字段名需推断；这里给最小可行集
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

        await s.commit()
    return {"company_id": 100, "contact_id": 200, "opportunity_id": 300}


# 便捷：直接构造 QuotationService（用于单元测试）
@pytest_asyncio.fixture
async def service(seeded_db):
    from plugins.ddw_quotation.services import QuotationService

    return QuotationService(seeded_db)


@pytest_asyncio.fixture
async def service_with_related(seeded_db, seeded_related):
    """同 service，但外键引用（company/contact/opportunity）已就位。"""
    from plugins.ddw_quotation.services import QuotationService

    return QuotationService(seeded_db)
