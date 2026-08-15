from __future__ import annotations

"""ddw_instance_binding 测试 conftest：注入 in-memory SQLite + 种子租户 + 占位 crm_companies/crm_licenses。

实例表的外键依赖：
- crm_companies  由 ddw_company_profile (P0-1) 提供
- crm_licenses   由 ddw_license_core  (P4-2) 提供

测试策略：conftest 自适应
- 若真实模型已注册到 Base.metadata（跨插件回归）→ 用真实 ORM
- 否则用最小 stub 行（仅 id 列 + 必要字段）
"""

import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from sqlalchemy import event
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
    """SQLite 内存数据库引擎（启用 FK 约束，支撑 SET NULL 行为）。"""
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
    """构造 sessionmaker，建表（含核心模型 + 本插件模型 + 缺失关联表占位）。"""
    # 本插件的 FK 引用 crm_companies 和 crm_licenses。
    # 主动尝试 import 依赖插件的 models；跨插件回归时由根 conftest 加载，独立测试时由本 conftest 兜底。
    from sqlalchemy import Column, Integer, String, Table

    from core.database import models  # noqa: F401  触发核心模型注册
    from core.database.session import Base
    from plugins.ddw_instance_binding import models as plugin_models  # noqa: F401

    try:
        from plugins.ddw_company_profile import models as _cp_models  # noqa: F401
    except ImportError:
        pass
    try:
        from plugins.ddw_license_core import models as _lc_models  # noqa: F401
    except ImportError:
        pass

    # 兜底：若依赖插件未加载，建最小 stub 表让 metadata.create_all 成功
    for tbl_name in ("crm_companies", "crm_licenses"):
        if tbl_name not in Base.metadata.tables:
            Table(
                tbl_name,
                Base.metadata,
                Column("id", Integer, primary_key=True, autoincrement=True),
                Column("tenant_id", Integer, nullable=True),
                Column("name", String(200), nullable=True),
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
async def seeded_company(session_factory):
    """插入 crm_companies 行（id=100），供 Instance.company_id 外键引用。

    自适应：
    - 若 crm_companies 是真实 Company 模型（ddw_company_profile 加载过）→ 用 Company ORM
    - 否则用最小 stub 行
    """
    from sqlalchemy import insert

    from core.database.session import Base

    companies_tbl = Base.metadata.tables["crm_companies"]
    # 用"credit_code"作为真伪判别：真实 Company 有此列，stub 表没有
    is_real_company = "credit_code" in companies_tbl.c
    async with session_factory() as s:
        if is_real_company:
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
                        id=100, tenant_id=1, name="测试客户公司"
                    )
                )
        else:
            await s.execute(insert(companies_tbl).values(id=100, tenant_id=1))
        await s.commit()
    return 100


@pytest_asyncio.fixture
async def seeded_license(session_factory, seeded_company):
    """插入 crm_licenses 行（id=200），供 Instance.license_id 外键引用。

    自适应：若真实 License 模型已注册到 metadata → 用 ORM；否则用最小 stub 行。
    """
    from sqlalchemy import insert

    from core.database.session import Base

    licenses_tbl = Base.metadata.tables["crm_licenses"]
    async with session_factory() as s:
        if "license_no" in licenses_tbl.c:
            try:
                from plugins.ddw_license_core.models import License

                s.add(
                    License(
                        id=200,
                        tenant_id=1,
                        company_id=100,
                        license_no="LIC-TEST-200",
                        license_type="formal",
                        valid_from=__import__("datetime").date(2026, 1, 1),
                        valid_to=__import__("datetime").date(2027, 1, 1),
                        status="active",
                        product_ids=[],
                        plugin_entitlements=[],
                    )
                )
            except (ImportError, Exception):  # noqa: BLE001
                await s.execute(
                    insert(licenses_tbl).values(
                        id=200, tenant_id=1, company_id=100
                    )
                )
        else:
            await s.execute(
                insert(licenses_tbl).values(id=200, tenant_id=1, company_id=100)
            )
        await s.commit()
    return 200


# 便捷：直接构造 InstanceService（用于单元测试）
@pytest_asyncio.fixture
async def service(seeded_db):
    from plugins.ddw_instance_binding.services import InstanceService

    return InstanceService(seeded_db)


@pytest_asyncio.fixture
async def service_with_deps(seeded_db, seeded_company, seeded_license):
    """同 service，但 crm_companies (id=100) 和 crm_licenses (id=200) 已就位。"""
    from plugins.ddw_instance_binding.services import InstanceService

    return InstanceService(seeded_db)
