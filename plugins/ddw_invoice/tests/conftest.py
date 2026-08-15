from __future__ import annotations

"""ddw_invoice 测试 conftest：注入 in-memory SQLite + 种子租户 + 占位 crm_companies / crm_orders。

发票表的外键依赖 crm_companies / crm_orders 两张表：
- crm_companies  由 ddw_company_profile (P0-1) 提供
- crm_orders     由 P1-2 ddw_order 提供

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
    """为 crm_companies / crm_orders 注册 stub（仅含 id），让 FK 元数据完整。

    真实表由 P0-1 / P1-2 插件提供；独立测试环境只需让 create_all 通过。
    已有真实模型时直接 import 触发注册，不再重复 stub。
    """
    from sqlalchemy import BigInteger, Column, Integer, String, Table

    from core.database.session import Base

    BigInt = BigInteger().with_variant(Integer(), "sqlite")

    # crm_companies stub
    if "crm_companies" not in Base.metadata.tables:
        Table(
            "crm_companies",
            Base.metadata,
            Column("id", BigInt, primary_key=True, autoincrement=True),
            Column("tenant_id", BigInt, nullable=False, index=True),
            Column("name", String(200), nullable=False, server_default=""),
        )

    # crm_orders stub
    if "crm_orders" not in Base.metadata.tables:
        Table(
            "crm_orders",
            Base.metadata,
            Column("id", BigInt, primary_key=True, autoincrement=True),
            Column("tenant_id", BigInt, nullable=False, index=True),
            Column("order_no", String(50), nullable=False, server_default=""),
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
        "plugins.ddw_partner_directory",
        "plugins.ddw_lead_claim",
        "plugins.ddw_voice_capture",
        "plugins.ddw_sales_note",
        "plugins.ddw_transcript_ai",
        "plugins.ddw_sales_copilot",
        "plugins.ddw_product_catalog",
        "plugins.ddw_license_core",
        "plugins.ddw_instance_binding",
        "plugins.ddw_token_entitlement",
        "plugins.ddw_support_ticket",
        "plugins.ddw_renewal",
        "plugins.ddw_signature_adapter",
    ):
        try:
            __import__(f"{plugin_pkg}.models", fromlist=["*"])
        except ImportError:
            pass

    from plugins.ddw_invoice import models as invoice_models  # noqa: F401

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
    """插入 crm_companies 行（id=100），供 Invoice.company_id 外键引用。"""
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
                try:
                    await s.execute(
                        insert(companies_tbl).values(
                            id=100, name="测试客户公司", status="active"
                        )
                    )
                except Exception:  # noqa: BLE001
                    await s.execute(insert(companies_tbl).values(id=100, name="测试客户公司"))
        else:
            await s.execute(insert(companies_tbl).values(id=100))
        await s.commit()
    return 100


@pytest_asyncio.fixture
async def seeded_order(session_factory, seeded_company):
    """插入 crm_orders 行（id=200），供 Invoice.order_id 外键引用。"""
    from sqlalchemy import insert

    from core.database.session import Base

    orders_tbl = Base.metadata.tables["crm_orders"]
    async with session_factory() as s:
        if "order_no" in orders_tbl.c:
            try:
                from plugins.ddw_order.models import Order

                s.add(
                    Order(
                        id=200,
                        tenant_id=1,
                        company_id=100,
                        order_no="ORD-2026-0001",
                        status="confirmed",
                    )
                )
            except (ImportError, Exception):  # noqa: BLE001
                try:
                    await s.execute(
                        insert(orders_tbl).values(
                            id=200,
                            tenant_id=1,
                            order_no="ORD-2026-0001",
                        )
                    )
                except Exception:  # noqa: BLE001
                    await s.execute(insert(orders_tbl).values(id=200))
        else:
            await s.execute(insert(orders_tbl).values(id=200))
        await s.commit()
    return 200


@pytest_asyncio.fixture
async def seeded_company_with_invoice_info(session_factory, seeded_company):
    """在 crm_companies 行（id=100）上补充 invoice_title / tax_id 字段。

    request_by_customer 服务依赖这两个字段做自动填充。
    """
    from sqlalchemy import update

    from core.database.session import Base

    companies_tbl = Base.metadata.tables["crm_companies"]
    async with session_factory() as s:
        try:
            await s.execute(
                update(companies_tbl)
                .where(companies_tbl.c.id == 100)
                .values(
                    invoice_title="武汉测试客户公司",
                    tax_id="91420100MA0000000X",
                )
            )
            await s.commit()
        except Exception:  # noqa: BLE001
            # stub 表可能不含 invoice_title / tax_id 列；跳过
            await s.rollback()
    return 100


# 便捷：直接构造 InvoiceService（用于单元测试）
@pytest_asyncio.fixture
async def service(seeded_db):
    from plugins.ddw_invoice.services import InvoiceService

    return InvoiceService(seeded_db)


@pytest_asyncio.fixture
async def service_with_company(seeded_db, seeded_company):
    """同 service，但 crm_companies 占位行（id=100）已就位。"""
    from plugins.ddw_invoice.services import InvoiceService

    return InvoiceService(seeded_db)


@pytest_asyncio.fixture
async def service_with_order(seeded_db, seeded_company, seeded_order):
    """同 service，但 crm_companies（id=100）和 crm_orders（id=200）占位行都已就位。"""
    from plugins.ddw_invoice.services import InvoiceService

    return InvoiceService(seeded_db)
