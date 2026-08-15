from __future__ import annotations

from typing import Optional

"""ddw_reconciliation 测试 conftest：注入 in-memory SQLite + 种子租户 + 种子企业。

本插件**不创建新表**，直接 query / update P1-3 crm_receivables 与 P1-4 crm_offline_pos_records。

依赖注册：
- crm_companies  ← 来自 ddw_company_profile (P0-1)
- crm_contacts   ← 来自 ddw_contact_hub (P0-2)  — receivable 不直接引用，但 contact_hub 会在 metadata 注册
- crm_orders     ← 来自 ddw_order (P1-2)  — receivable FK
- crm_contracts  ← 来自 ddw_contract_core (P1-1)  — receivable FK
- crm_receivables← 来自 ddw_receivable (P1-3)
- crm_offline_pos_records   ← 来自 ddw_offline_pos (P1-4)

为保险起见，对未被真实模型注册的关联表（独立跑本插件时）建仅含 id 的 stub。
"""

import sys
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path

import pytest_asyncio
from sqlalchemy import BigInteger, Column, Integer, String, Table
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
# 模块级：注册本插件不直接创建、但其 ORM 模型会被引用的依赖插件的 models。
# 同时为缺失的关联表注册 stub（仅含 id）。
#
# 关键：占位表必须在模块级加（不能只在 session_factory fixture 内加），
# 避免 pytest 跨插件串跑时 crm_orders / crm_contracts 等表因 stub 缺失而
# metadata.create_all 抛 NoReferencedTableError。
# ---------------------------------------------------------------------------
from core.database import models as _core_models  # noqa: E402, F401
from core.database.session import Base  # noqa: E402

# 真实插件的模型（Pytest session 启动时 conftest.py 也会再注册一次，幂等）
for _plugin_pkg in (
    "plugins.ddw_company_profile",
    "plugins.ddw_contact_hub",
    "plugins.ddw_opportunity",
    "plugins.ddw_quotation",
    "plugins.ddw_order",
    "plugins.ddw_contract_core",
    "plugins.ddw_receivable",
    "plugins.ddw_offline_pos",
):
    try:
        __import__(f"{_plugin_pkg}.models", fromlist=["*"])
    except ImportError:
        pass

# 兜底 stub：crm_companies / crm_contacts / crm_orders / crm_contracts
# 真实表已被注册时不重复（dict 行为）。
BigInt = BigInteger().with_variant(Integer(), "sqlite")
_STUB_DEFS = {
    "crm_companies": [
        Column("id", BigInt, primary_key=True, autoincrement=True),
        Column("tenant_id", BigInt, nullable=False, index=True),
        Column("name", String(200), nullable=False, server_default=""),
    ],
    "crm_contacts": [
        Column("id", BigInt, primary_key=True, autoincrement=True),
        Column("tenant_id", BigInt, nullable=False, index=True),
        Column("name", String(200), nullable=False, server_default=""),
    ],
    "crm_orders": [
        Column("id", BigInt, primary_key=True, autoincrement=True),
        Column("tenant_id", BigInt, nullable=False, index=True),
        Column("order_no", String(50), nullable=False, server_default=""),
    ],
    "crm_contracts": [
        Column("id", BigInt, primary_key=True, autoincrement=True),
        Column("tenant_id", BigInt, nullable=False, index=True),
        Column("contract_no", String(50), nullable=False, server_default=""),
    ],
}
for _tbl_name, _cols in _STUB_DEFS.items():
    if _tbl_name not in Base.metadata.tables:
        Table(_tbl_name, Base.metadata, *_cols)


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
    """构造 sessionmaker，建表。"""
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
    """插入 crm_companies id=100（测试客户公司），返回 company_id=100。

    自适应：
    - 若 crm_companies 是真实 Company 模型 → 用 Company ORM
    - 否则用 stub 表（仅含 id + name）插入
    """
    from sqlalchemy import insert

    async with session_factory() as s:
        companies_tbl = Base.metadata.tables["crm_companies"]
        if "name" in companies_tbl.c and "status" in companies_tbl.c:
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
                await s.execute(
                    insert(companies_tbl).values(
                        id=100,
                        tenant_id=1,
                        name="测试客户公司",
                    )
                )
        else:
            await s.execute(
                insert(companies_tbl).values(id=100, tenant_id=1, name="测试客户公司")
            )
        await s.commit()
    return 100


# ---------------------------------------------------------------------------
# 便捷 fixtures：构造核销场景用的 Receivable / Payment
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def make_receivable(seeded_db):
    """返回一个 async factory，直接创建 Receivable 并 flush。"""
    from datetime import date

    from plugins.ddw_receivable.models import Receivable

    async def _factory(
        *,
        node_name: str = "首款",
        amount: Decimal = Decimal("10000.00"),
        paid_amount: Decimal = Decimal(0),
        company_id: int = 100,
        due_date=None,
        status: str = "pending",
    ) -> Receivable:
        r = Receivable(
            tenant_id=1,
            company_id=company_id,
            node_name=node_name,
            amount=amount,
            paid_amount=paid_amount,
            due_date=due_date or date.today(),
            status=status,
        )
        seeded_db.add(r)
        await seeded_db.flush()
        await seeded_db.refresh(r)
        return r

    return _factory


@pytest_asyncio.fixture
async def make_payment(seeded_db, seeded_company):
    """返回一个 async factory，直接创建 Payment 并 flush。"""
    from datetime import date

    from plugins.ddw_offline_pos.models import Payment
    from plugins.ddw_offline_pos.services import generate_payment_no

    async def _factory(
        *,
        payer_name: str = "测试客户公司",
        amount: Decimal = Decimal("10000.00"),
        matched_amount: Decimal = Decimal(0),
        company_id: int = 100,
        payment_date=None,
        payment_method: str = "bank",
        status: str = "pending",
        payment_no: Optional[str] = None,
    ) -> Payment:
        # payment_no 是 NOT NULL；不显式传时调用真实生成器（与 P1-4 服务一致）
        if payment_no is None:
            payment_no = await generate_payment_no(seeded_db)
        p = Payment(
            tenant_id=1,
            company_id=company_id,
            payment_no=payment_no,
            payer_name=payer_name,
            amount=amount,
            matched_amount=matched_amount,
            payment_date=payment_date or date.today(),
            payment_method=payment_method,
            status=status,
        )
        seeded_db.add(p)
        await seeded_db.flush()
        await seeded_db.refresh(p)
        return p

    return _factory


@pytest_asyncio.fixture(autouse=True)
def reset_history():
    """每个测试前清空内存历史与分配表，避免互相污染。"""
    from plugins.ddw_reconciliation.services import clear_history

    clear_history()
    yield
    clear_history()


# ---------------------------------------------------------------------------
# 便捷：直接构造 ReconciliationService
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def service(seeded_db):
    from plugins.ddw_reconciliation.services import ReconciliationService

    return ReconciliationService(seeded_db)


@pytest_asyncio.fixture
async def service_with_company(seeded_db, seeded_company):
    from plugins.ddw_reconciliation.services import ReconciliationService

    return ReconciliationService(seeded_db)
