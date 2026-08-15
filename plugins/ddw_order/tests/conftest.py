from __future__ import annotations

"""ddw_order 测试 conftest：注入 in-memory SQLite + 种子租户。"""

import sys
from collections.abc import AsyncIterator
from pathlib import Path

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


# ---------------------------------------------------------------------------
# 模块级：注册本插件的 ORM 模型到 Base.metadata + 给缺失的关联表加占位。
#
# 关键：占位表必须在模块级加（不能只在 session_factory fixture 内加），
# 因为 pytest 跨插件串跑时：
#   1) 本 conftest 模块级 import 触发 crm_orders 注册到 Base.metadata
#   2) 其他插件的 session_factory fixture 跑时调用 Base.metadata.create_all
#   3) create_all 走全表，遇到 crm_orders 的 FK (crm_contracts) 时若占位表
#      不在 metadata 会抛 NoReferencedTableError
# 真实生产环境由 ddw_company_profile / ddw_contract_core 提供；独立测试时
# 占位表只含 id，零业务字段。
# ---------------------------------------------------------------------------
from core.database import models as _core_models  # noqa: E402, F401
from core.database.session import Base  # noqa: E402
from plugins.ddw_order import models as _order_models  # noqa: E402, F401

for _tbl_name in ("crm_companies", "crm_contracts"):
    if _tbl_name not in Base.metadata.tables:
        Table(
            _tbl_name,
            Base.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
        )


@pytest_asyncio.fixture
async def engine():
    """SQLite 内存数据库引擎（启用 FK 约束，支撑 CASCADE 行为）。"""
    from sqlalchemy import event

    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite 默认不强制 FK
    @event.listens_for(eng.sync_engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    """构造 sessionmaker，建表（占位表已在模块级加好）。"""
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
    """在 crm_companies 塞一个 id=100 的公司，返回 company_id=100。

    兼容两种情况：
    - P0-1 ddw_company_profile 已加载：用真实 Company 模型（带 NOT NULL 字段）
    - 独立测试：用占位表（仅 id）插入即可
    """
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
            except (ImportError, Exception):  # noqa: BLE001
                await s.execute(
                    insert(companies_tbl).values(
                        id=100, name="测试客户公司", status="active",
                        certification_status="pending", tags="[]",
                    )
                )
        else:
            await s.execute(insert(companies_tbl).values(id=100))
        await s.commit()
    return 100


@pytest_asyncio.fixture
async def service(seeded_db):
    """基础 OrderService（无 company/contract 关联）。"""
    from plugins.ddw_order.services import OrderService

    return OrderService(seeded_db)
