from __future__ import annotations

"""ddw_lead_claim 测试 conftest：注入 in-memory SQLite + 种子租户/企业/渠道。

依赖关系：
- crm_companies  由 ddw_company_profile (P0-1) 提供（真实模型）
- crm_partners  由 P2-1 ddw_partner_directory 提供（实际未建，需 stub）

测试策略：先尝试 import 已存在的真实模型，否则用 SQLAlchemy ``Table``
直接注册仅含 id 的 stub 表，让 metadata.create_all 阶段 FK 引用能 resolve。
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


def _register_stub_tables() -> None:
    """为 crm_partners 注册 stub（仅含 id/tenant_id），让 FK 元数据完整。

    真实表由 P2-1 ddw_partner_directory 插件提供；独立测试环境只需让
    create_all 通过。已有真实模型时直接 import 触发注册，不再重复 stub。
    """
    from sqlalchemy import BigInteger, Column, Integer, String, Table

    from core.database.session import Base

    BigInt = BigInteger().with_variant(Integer(), "sqlite")

    if "crm_partners" not in Base.metadata.tables:
        Table(
            "crm_partners",
            Base.metadata,
            Column("id", BigInt, primary_key=True, autoincrement=True),
            Column("tenant_id", BigInt, nullable=False, index=True),
            Column("name", String(120), nullable=False, server_default=""),
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
    """构造 sessionmaker，并建表（含核心模型 + 本插件模型 + 缺失的关联表占位）。"""
    from core.database import models  # noqa: F401  触发核心模型注册
    from core.database.session import Base

    # 触发所有已知插件的真实模型注册（FK 目标表必须在 metadata 里）
    for plugin_pkg in (
        "plugins.ddw_company_profile",
        "plugins.ddw_contact_hub",
        "plugins.ddw_opportunity",
        "plugins.ddw_quotation",
        "plugins.ddw_sales_dashboard",
        "plugins.ddw_order",
        "plugins.ddw_contract_core",
        "plugins.ddw_receivable",
        "plugins.ddw_offline_pos",
        "plugins.ddw_reconciliation",
        "plugins.ddw_finance_dashboard",
    ):
        try:
            __import__(f"{plugin_pkg}.models", fromlist=["*"])
        except ImportError:
            pass

    from plugins.ddw_lead_claim import models as claim_models  # noqa: F401

    _register_stub_tables()

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
async def seeded_company(session_factory, seeded_tenant):
    """插入 crm_companies 行（id=100），供 LeadClaim.company_id 外键引用。

    自适应：
    - 若 crm_companies 是真实 Company 模型（ddw_company_profile 加载过）→ 用 Company ORM
    - 否则用最小 stub 行（仅 id 列）
    """
    from sqlalchemy import insert

    from core.database.session import Base

    companies_tbl = Base.metadata.tables["crm_companies"]
    async with session_factory() as s:
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
            except (ImportError, Exception):  # noqa: BLE001
                # 兜底：直接最小行
                await s.execute(
                    insert(companies_tbl).values(
                        id=100, name="测试客户公司", status="active"
                    )
                )
        else:
            await s.execute(insert(companies_tbl).values(id=100))
        await s.commit()
    return 100


@pytest_asyncio.fixture
async def seeded_partner(session_factory, seeded_tenant):
    """插入 crm_partners 占位行（id=200），供 LeadClaim.partner_id 外键引用。"""
    from sqlalchemy import insert

    from core.database.session import Base

    partners_tbl = Base.metadata.tables["crm_partners"]

    # 真实 ORM 模型：crm_partners 由 P2-1 ddw_partner_directory 注册，含 partner_type/level 等 NOT NULL 字段
    # 此时用 ORM Session.add 走完整字段
    if "partner_type" in partners_tbl.c:
        from plugins.ddw_partner_directory.models import Partner

        async with session_factory() as s:
            s.add(
                Partner(
                    id=200,
                    tenant_id=1,
                    partner_type="reseller",
                    level="normal",
                    product_discount=80,
                    plugin_discount=85,
                    service_discount=90,
                    status="active",
                )
            )
            await s.commit()
        return 200

    # stub 表：只含 id/tenant_id/name
    async with session_factory() as s:
        if "name" in partners_tbl.c:
            await s.execute(
                insert(partners_tbl).values(id=200, tenant_id=1, name="测试渠道伙伴 A")
            )
        else:
            await s.execute(insert(partners_tbl).values(id=200))
        await s.commit()
    return 200


# 便捷：直接构造 LeadClaimService（用于单元测试）
@pytest_asyncio.fixture
async def service(seeded_db):
    from plugins.ddw_lead_claim.services import LeadClaimService

    return LeadClaimService(seeded_db)


@pytest_asyncio.fixture
async def service_with_company(seeded_db, seeded_company):
    """同 service，但 crm_companies 行（id=100）已就位。"""
    from plugins.ddw_lead_claim.services import LeadClaimService

    return LeadClaimService(seeded_db)


@pytest_asyncio.fixture
async def service_full(seeded_db, seeded_company, seeded_partner):
    """service + company(id=100) + partner(id=200) 三者就位。"""
    from plugins.ddw_lead_claim.services import LeadClaimService

    return LeadClaimService(seeded_db)
