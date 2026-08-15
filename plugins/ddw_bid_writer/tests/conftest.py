"""ddw_bid_writer 测试 conftest：注入 in-memory SQLite。"""

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

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    from core.database import models  # noqa: F401
    from core.database.session import Base
    from plugins.ddw_bid_writer import models as plugin_models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    return async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncIterator[AsyncSession]:
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def seeded_tenant(session_factory):
    from core.database.models import Tenant

    async with session_factory() as s:
        s.add(Tenant(id=1, name="测试设计院", plan="pro", status="active"))
        await s.commit()
    return 1


@pytest.fixture
def template_service():
    from plugins.ddw_bid_writer.services import TemplateService
    return TemplateService()


@pytest.fixture
def generate_service():
    from plugins.ddw_bid_writer.services import GenerateService
    return GenerateService(use_llm=False)


@pytest.fixture
def style_service():
    from plugins.ddw_bid_writer.services import StyleService
    return StyleService()


@pytest.fixture
def review_service():
    from plugins.ddw_bid_writer.services import ReviewService
    return ReviewService()
