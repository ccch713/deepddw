from __future__ import annotations

"""ddw_receivable 测试 conftest：注入 in-memory SQLite + 种子租户。

应收表的外键依赖 crm_companies / crm_orders / crm_contracts 三张表：
- crm_companies  由 ddw_company_profile (P0-1) 提供
- crm_orders    由 P1-2  提供（实际未建，需 stub）
- crm_contracts 由 P1-1  提供（实际未建，需 stub）

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
    """为 crm_orders / crm_contracts 注册 stub（仅含 id），让 FK 元数据完整。

    真实表由 P1-1 / P1-2 插件提供；独立测试环境只需让 create_all 通过。
    已有真实模型时直接 import 触发注册，不再重复 stub。
    """
    from sqlalchemy import BigInteger, Column, Integer, String, Table

    from core.database.session import Base

    BigInt = BigInteger().with_variant(Integer(), "sqlite")

    # crm_orders stub
    if "crm_orders" not in Base.metadata.tables:
        Table(
            "crm_orders",
            Base.metadata,
            Column("id", BigInt, primary_key=True, autoincrement=True),
            Column("tenant_id", BigInt, nullable=False, index=True),
            Column("order_no", String(50), nullable=False, server_default=""),
        )

    # crm_contracts stub
    if "crm_contracts" not in Base.metadata.tables:
        Table(
            "crm_contracts",
            Base.metadata,
            Column("id", BigInt, primary_key=True, autoincrement=True),
            Column("tenant_id", BigInt, nullable=False, index=True),
            Column("contract_no", String(50), nullable=False, server_default=""),
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
    ):
        try:
            __import__(f"{plugin_pkg}.models", fromlist=["*"])
        except ImportError:
            pass

    from plugins.ddw_receivable import models as recv_models  # noqa: F401

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
    """插入一个测试 company，返回 company_id。"""
    from sqlalchemy import insert

    from core.database.session import Base

    async with session_factory() as s:
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
        await s.commit()
    return 100


# 便捷：直接构造 ReceivableService（用于单元测试）
@pytest_asyncio.fixture
async def service(seeded_db):
    from plugins.ddw_receivable.services import ReceivableService

    return ReceivableService(seeded_db)


@pytest_asyncio.fixture
async def service_with_company(seeded_db, seeded_company):
    """同 service，但 crm_companies 已就位可用。"""
    from plugins.ddw_receivable.services import ReceivableService

    return ReceivableService(seeded_db)
