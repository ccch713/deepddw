from __future__ import annotations

"""ddw_account_linker 测试 conftest：注入 in-memory SQLite + 种子租户 + 占位 crm_companies。

关键：
- 模块级 import 触发 AccountLink 注册到 Base.metadata
- 模块级给缺失的 crm_companies 加占位表（独立测试时使用）
  跨插件串跑时，根 conftest.py 已预先 import ddw_company_profile 注入真实表
- engine fixture 启用 PRAGMA foreign_keys=ON（支撑 SET NULL 行为）
- seeded_company 兼容真实 Company 模型 / 占位表两种情况
"""

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
# 模块级：注册 ORM 模型到 Base.metadata + 占位 crm_companies
#
# 占位表必须在模块级加：跨插件串跑时，其他插件的 session_factory fixture
# 跑 Base.metadata.create_all 时若 crm_companies 不在 metadata 会抛
# NoReferencedTableError。真实生产环境由 ddw_company_profile 提供；
# 独立测试时占位表只含 id。
# ---------------------------------------------------------------------------
from core.database import models as _core_models  # noqa: E402, F401
from core.database.session import Base  # noqa: E402
from plugins.ddw_account_linker import (
    models as _account_link_models,  # noqa: E402, F401
)

for _tbl_name in ("crm_companies",):
    if _tbl_name not in Base.metadata.tables:
        Table(
            _tbl_name,
            Base.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
        )


@pytest_asyncio.fixture
async def engine():
    """SQLite 内存数据库引擎（启用 FK 约束，支撑 ON DELETE SET NULL 行为）。"""
    from sqlalchemy import event

    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite 默认不强制 FK，导致 ON DELETE SET NULL 不生效
    @event.listens_for(eng.sync_engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

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
                # 兜底：raw insert（必填字段最小集）
                await s.execute(
                    insert(companies_tbl).values(
                        id=100,
                        name="测试客户公司",
                        status="active",
                        certification_status="pending",
                        tags="[]",
                    )
                )
        else:
            await s.execute(insert(companies_tbl).values(id=100))
        await s.commit()
    return 100


# 便捷：直接构造 AccountLinkService（用于单元测试）
@pytest_asyncio.fixture
async def service(seeded_db):
    from plugins.ddw_account_linker.services import AccountLinkService

    return AccountLinkService(seeded_db)


@pytest_asyncio.fixture
async def seeded_company2(session_factory, seeded_tenant):
    """在 crm_companies 塞一个 id=999 的公司（用于多企业隔离测试），返回 company_id=999。

    兼容真实 Company 模型 / 占位表两种情况。
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
                        id=999,
                        tenant_id=1,
                        name="另一家测试公司",
                        status="active",
                        certification_status="pending",
                        tags=[],
                    )
                )
            except (ImportError, Exception):  # noqa: BLE001
                await s.execute(
                    insert(companies_tbl).values(
                        id=999,
                        name="另一家测试公司",
                        status="active",
                        certification_status="pending",
                        tags="[]",
                    )
                )
        else:
            await s.execute(insert(companies_tbl).values(id=999))
        await s.commit()
    return 999
