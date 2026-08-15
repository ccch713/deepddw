"""ddw_docs_portal 测试夹具（deepDDW 开源裁剪版）。

策略：mock 外部依赖，不碰真实服务：
- in-memory SQLite（StaticPool）+ Base.metadata.create_all
- 记忆写入（core.knowledge.memory_put）走独立文件库 → monkeypatch 到 tmp 路径
- HTTP 层：轻量 FastAPI app 仅挂 build_router()，monkeypatch session maker 指向内存库
- 鉴权：deepDDW 静态访问 Token（DDW_ACCESS_TOKEN 测试值）
"""
from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

os.environ.setdefault("DDW_ACCESS_TOKEN", "test-token-docs-portal")

# 平台根目录入 sys.path（独立跑插件测试时）
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.database.session import Base, session_scope  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

# 触发 docs_* 三张表注册到 Base.metadata
from plugins.ddw_docs_portal import models as _portal_models  # noqa: E402,F401
from plugins.ddw_docs_portal.services import DocsPortalService  # noqa: E402

# ─── 用户上下文（token 门禁 claims 结构；单用户超级管理员） ──────

SUPERADMIN = {"user_id": 0, "tenant_id": 0, "role": "superadmin"}
MEMBER_A = {"user_id": 10, "tenant_id": 0, "role": "member"}


# ─── fixtures ──────────────────────────────────────────────────


@pytest.fixture
def memory_db(tmp_path, monkeypatch):
    """把 core.knowledge 的文件库指向 tmp 目录（不污染真实 data/）。"""
    db_file = tmp_path / "ddw_main.db"

    def _fake_path():
        return db_file

    monkeypatch.setattr("core.knowledge._db_path", _fake_path)
    return db_file


@pytest_asyncio.fixture
async def engine() -> AsyncIterator:
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def patch_session(monkeypatch, engine):
    """把平台 session maker 指向内存库（session_scope 生效）。"""

    def _patch():
        from core.database import session as db_session

        maker = async_sessionmaker(
            bind=engine, expire_on_commit=False, class_=AsyncSession
        )
        monkeypatch.setattr(db_session, "_session_maker", maker)
        monkeypatch.setattr(db_session, "_engine", engine)
        return maker

    return _patch


@pytest_asyncio.fixture
async def service(engine, patch_session, memory_db) -> DocsPortalService:
    """业务服务（内存库）。"""
    patch_session()
    async with session_scope() as db:
        yield DocsPortalService(db)


@pytest_asyncio.fixture
async def client(engine, patch_session, memory_db):
    """HTTP 客户端：仅挂载本插件 router（轻量，不加载全平台）。"""
    import httpx
    from fastapi import FastAPI
    from httpx import ASGITransport

    from plugins.ddw_docs_portal.router import build_router

    patch_session()
    app = FastAPI()
    app.include_router(build_router())
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def token_superadmin() -> str:
    from core.security.token_gate import get_access_token

    return get_access_token()


@pytest.fixture
def auth_headers(token_superadmin) -> dict:
    return {"Authorization": f"Bearer {token_superadmin}"}
