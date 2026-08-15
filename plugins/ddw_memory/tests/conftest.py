"""ddw_memory 测试 fixtures — 每个测试函数重建 engine + 表。"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))
_plug_dir = str(_repo_root / "plugins" / "ddw_memory")
if _plug_dir not in sys.path:
    sys.path.insert(0, _plug_dir)




@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """每个测试前：新建 engine + 建表 + 插入测试租户，测试后销毁。"""
    import core.database.session as db_session_mod
    from core.database.models import Tenant
    from core.database.session import Base
    from plugins.ddw_memory.models import (  # noqa: F401
        AutoCaptureConfigORM,
        AutoCapturePendingORM,
        MemoryORM,
        PositionSOPTemplateORM,
    )

    # 每次创建新 engine（不用模块级单例，避免跨 run 泄漏）
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    sm = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    db_session_mod._engine = engine
    db_session_mod._session_maker = sm

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with sm() as session:
        session.add(Tenant(id=1, name="Default", plan="free", status="active"))
        session.add(Tenant(id=16, name="祥云化工", plan="enterprise", status="active"))
        await session.commit()

    yield

    db_session_mod._engine = None
    db_session_mod._session_maker = None
    await engine.dispose()
