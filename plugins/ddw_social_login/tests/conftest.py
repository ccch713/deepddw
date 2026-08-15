"""ddw_social_login 测试 conftest：注入 in-memory SQLite + FastAPI TestClient。"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
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
# 数据库 fixtures
# ---------------------------------------------------------------------------


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
    """构造 sessionmaker，并建表。"""
    # 使用 core.database.models 中的 Base 和模型（唯一来源，避免重复注册）
    from core.database.session import Base
    import core.database.models  # noqa: F401 — 注册 User/Tenant/UserBinding/LoginAudit 等

    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, checkfirst=True))

    return async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncIterator[AsyncSession]:
    """干净的 session。"""
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def seeded_tenant(session_factory):
    """插入默认租户 id=1。"""
    from core.database.models import Tenant

    async with session_factory() as s:
        s.add(Tenant(id=1, name="测试租户", plan="pro", status="active"))
        await s.commit()
    return 1


@pytest_asyncio.fixture
async def seeded_db(session_factory, seeded_tenant) -> AsyncIterator[AsyncSession]:
    """带种子租户的 session。"""
    async with session_factory() as s:
        yield s


# ---------------------------------------------------------------------------
# FastAPI app + TestClient
# ---------------------------------------------------------------------------


@pytest.fixture
def config_manager():
    """预配置的 ConfigManager（钉钉已配置）。"""
    from plugins.ddw_social_login.config_manager import ConfigManager

    return ConfigManager({
        "auto_register": True,
        "default_tenant_id": 1,
        "allowed_callback_domains": ["ddw.9cio.com", "localhost"],
        "channels": {
            "dingtalk": {
                "enabled": True,
                "appid": "ding_test_appid",
                "app_secret": "ding_test_secret_123456",
                "callback_url": None,
            },
            "wechat_open": {
                "enabled": True,
                "appid": "wx_test_appid",
                "app_secret": "wx_test_secret_123456",
                "callback_url": None,
            },
            "qq": {"enabled": False, "appid": None, "app_secret": None, "callback_url": None},
            "feishu": {"enabled": False, "appid": None, "app_secret": None, "callback_url": None},
        },
    })


@pytest.fixture
def app(config_manager) -> FastAPI:
    """构造测试用 FastAPI app。"""
    from fastapi import FastAPI

    from plugins.ddw_social_login.router import build_router

    application = FastAPI()
    router = build_router(config_manager)
    application.include_router(router)
    return application


@pytest.fixture
def client(app):
    """构造同步 TestClient。"""
    from fastapi.testclient import TestClient

    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_social_user():
    """模拟 senweaver-oauth 返回的 AuthUser。"""
    user = MagicMock()
    user.uuid = "test_openid_1234567890abcdef"
    user.nickname = "测试用户"
    user.avatar = "https://example.com/avatar.jpg"
    user.username = "test_user"
    return user


@pytest.fixture
def mock_auth_response_success(mock_social_user):
    """模拟 senweaver-oauth 成功的 AuthResponse。"""
    response = MagicMock()
    response.code = 200
    response.data = mock_social_user
    response.message = "Success"
    return response


@pytest.fixture
def mock_auth_response_failure():
    """模拟 senweaver-oauth 失败的 AuthResponse。"""
    response = MagicMock()
    response.code = 400
    response.data = None
    response.message = "OAuth error"
    return response


def make_admin_token() -> str:
    """生成一个模拟的 admin JWT token。"""
    return "mock_admin_token_12345"


def make_user_token(user_id: int = 100, tenant_id: int = 1) -> str:
    """生成一个模拟的 user JWT token。"""
    return f"mock_user_token_{user_id}_{tenant_id}"
