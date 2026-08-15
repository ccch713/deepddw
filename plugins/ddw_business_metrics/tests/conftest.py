"""ddw_business_metrics 测试 conftest：注入 in-memory SQLite + 种子数据。

本插件是聚合查询插件，**不创建新表**，但 conftest 必须显式 import
依赖插件的 models，让它们注册到 Base.metadata / WalletBase.metadata，
否则后续 create_all 不会建立对应表。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import AsyncIterator

import pytest_asyncio
from sqlalchemy import Column, Integer, Table
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


def _ensure_stub_tables() -> None:
    """为 FK 依赖创建桩表（避免 import 整个插件）。"""
    from core.database.session import Base

    for tbl_name in ("crm_companies", "crm_contacts", "crm_contracts", "crm_partners"):
        if tbl_name not in Base.metadata.tables:
            Table(
                tbl_name,
                Base.metadata,
                Column("id", Integer, primary_key=True, autoincrement=True),
            )


@pytest_asyncio.fixture
async def engine():
    """SQLite 内存数据库引擎（FK 约束关闭，因使用桩表隔离依赖插件）。"""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    """构造 sessionmaker，并建表。"""
    from core.database import models  # noqa: F401  触发核心模型注册
    from core.database.session import Base
    from plugins.ddw_wallet.models import WalletBase  # noqa: F401
    from plugins.ddw_wallet.models import RechargeOrder  # noqa: F401
    from plugins.ddw_saas_billing.models import UsageLog  # noqa: F401
    from plugins.ddw_lead_claim.models import LeadClaim  # noqa: F401
    from plugins.ddw_opportunity.models import Opportunity  # noqa: F401
    from plugins.ddw_order.models import Order  # noqa: F401

    _ensure_stub_tables()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(WalletBase.metadata.create_all)

    return async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def seeded_db(session_factory) -> AsyncIterator[AsyncSession]:
    """干净的 session。"""
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def service(seeded_db):
    """直接构造 MetricsService（用于单元测试）。"""
    from plugins.ddw_business_metrics.services import MetricsService

    return MetricsService(seeded_db)
