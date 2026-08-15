"""ddw_personnel_qual 测试 conftest：注入 in-memory SQLite。

不污染真实 DB：每个测试用临时内存数据库 + StaticPool。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

# 把项目根加进 sys.path
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@pytest_asyncio.fixture
async def engine():
    """每个测试一个全新的 in-memory aiosqlite 引擎。"""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    """session factory + 初始化所有表（含 tenants 基表、User 基表，本插件模型）。"""
    # 触发 import models 让 Base 知道所有 mapper
    from core.database import models  # noqa: F401
    from core.database.session import Base
    from plugins.ddw_personnel_qual import models as plugin_models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    return maker


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncIterator[AsyncSession]:
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def seeded_tenant(session_factory):
    """在 DB 里写一个 tenant，tenant_id=1，所有租户级表的 FK 都依赖它。"""
    from core.database.models import Tenant

    async with session_factory() as s:
        t = Tenant(id=1, name="测试设计院", plan="pro", status="active")
        s.add(t)
        await s.commit()
    return 1


@pytest.fixture
def cert_service():
    from plugins.ddw_personnel_qual.services import CertService
    return CertService()


@pytest.fixture
def expiry_service():
    from plugins.ddw_personnel_qual.services import ExpiryService
    return ExpiryService(warn_days=90)


@pytest.fixture
def renewal_service():
    from plugins.ddw_personnel_qual.services import RenewalService
    return RenewalService()
