"""测试配置：mock LLM + 内存 SQLite + mock 钱包 + 租户上下文。

租户说明（2026-08-14 分租户改造）：
- 租户过滤 hooks 是全局 Session 级事件，测试进程加载时安装一次
- autouse fixture 让所有测试默认处于 TEST_TENANT_ID 租户作用域
  （与真实请求经 TenantContextMiddleware 解析 JWT 的效果一致）
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.database.tenant_filter import (
    install_tenant_hooks,
    reset_tenant_context,
    set_tenant_context,
)

install_tenant_hooks(None)

TEST_TENANT_ID = 1


@pytest.fixture(autouse=True)
def tenant_context():
    """所有测试默认处于 TEST_TENANT_ID 租户作用域。"""
    token = set_tenant_context(TEST_TENANT_ID)
    yield
    reset_tenant_context(token)


@pytest.fixture
def mock_llm():
    """Mock LLM Gateway。"""
    mock = AsyncMock()
    mock.generate = AsyncMock(
        return_value="这是一个测试回答？"
    )
    return mock


@pytest.fixture
def mock_wallet_client():
    """Mock 钱包客户端。"""
    mock = AsyncMock()
    mock.charge = AsyncMock(
        return_value={
            "txn_no": "TXN_TEST_001",
            "balance_after_cents": 10000,
        }
    )
    mock.get_balance = AsyncMock(
        return_value={"balance_cents": 10000}
    )
    return mock


@pytest.fixture
def mock_session():
    """Mock 数据库会话。"""
    return MagicMock()
