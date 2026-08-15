"""会话生命周期 + 计费对接测试。"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plugins.ddw_wenqu_tutor.services.session import (
    add_message,
    create_session,
    end_session,
    update_active_seconds,
)


@pytest.fixture
def mock_db():
    """Mock 数据库会话（execute 返回空消息列表 → 用量 0）。"""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    def _empty_execute(*args, **kwargs):
        m = MagicMock()
        m.scalars.return_value.all.return_value = []
        return m

    db.execute = AsyncMock(side_effect=_empty_execute)
    return db


@pytest.fixture
def mock_wallet_client():
    """Mock 钱包客户端。"""
    client = AsyncMock()
    client.charge = AsyncMock(
        return_value={
            "txn_no": "TXN_TEST_001",
            "balance_after_cents": 10000,
        }
    )
    return client


@pytest.mark.asyncio
async def test_session_start(mock_db):
    """开课创建会话。"""
    session = await create_session(
        mock_db,
        student_name="CXY",
        subject="physics",
        chapter="力学",
    )
    assert session.id.startswith("WS")
    assert session.student_name == "CXY"
    assert session.subject == "physics"
    assert session.status == "active"
    assert mock_db.commit.called


@pytest.mark.asyncio
async def test_session_message_count(mock_db):
    """消息计数正确。"""
    # Mock get_session 返回
    mock_session = MagicMock()
    mock_session.id = "WS_TEST_001"
    mock_session.message_count = 0

    with patch(
        "plugins.ddw_wenqu_tutor.services.session.get_session",
        return_value=mock_session,
    ):
        await add_message(
            mock_db, "WS_TEST_001", "user", "你好"
        )
        # 验证 db.add 被调用（消息 + 事件）
        assert mock_db.add.call_count == 2
        assert mock_db.commit.called


@pytest.mark.asyncio
async def test_session_end_charges(
    mock_db, mock_wallet_client
):
    """下课计费正确。"""
    # Mock get_session 返回
    mock_session = MagicMock()
    mock_session.id = "WS_TEST_001"
    mock_session.student_name = "CXY"
    mock_session.subject = "physics"
    mock_session.status = "active"
    mock_session.active_seconds = 1800  # 30 分钟

    with patch(
        "plugins.ddw_wenqu_tutor.services.session.get_session",
        return_value=mock_session,
    ):
        result = await end_session(
            mock_db, "WS_TEST_001", mock_wallet_client
        )

        assert result["active_minutes"] == 30
        # M0-5 用量计费：无消息会话 → 最低 1 分（原 30×1200=36000 已弃用）
        assert result["charge_cents"] == 1
        assert result["txn_no"] == "TXN_TEST_001"
        assert result["balance_after_cents"] == 10000
        assert mock_wallet_client.charge.called


@pytest.mark.asyncio
async def test_session_end_idempotent(
    mock_db, mock_wallet_client
):
    """重复 end 不重复扣费（幂等）。"""
    mock_session = MagicMock()
    mock_session.id = "WS_TEST_001"
    mock_session.student_name = "CXY"
    mock_session.subject = "physics"
    mock_session.status = "active"
    mock_session.active_seconds = 1800

    with patch(
        "plugins.ddw_wenqu_tutor.services.session.get_session",
        return_value=mock_session,
    ):
        # 第一次下课
        await end_session(
            mock_db, "WS_TEST_001", mock_wallet_client
        )
        # 第二次下课（钱包会返回相同 txn_no）
        mock_session.status = "billed"
        try:
            await end_session(
                mock_db,
                "WS_TEST_001",
                mock_wallet_client,
            )
        except ValueError:
            pass  # 预期抛出异常

        # 钱包只应被调用一次
        assert mock_wallet_client.charge.call_count == 1


@pytest.mark.asyncio
async def test_session_idle_timeout(mock_db):
    """90s 无消息不累计活跃时间。"""
    session_id = "WS_TEST_001"
    mock_session = MagicMock()
    mock_session.id = session_id
    mock_session.active_seconds = 100

    with patch(
        "plugins.ddw_wenqu_tutor.services.session.get_session",
        return_value=mock_session,
    ):
        # 模拟 120 秒前的消息时间
        last_time = time.time() - 120
        elapsed = await update_active_seconds(
            mock_db, session_id, last_time
        )
        assert elapsed == 0  # 超时，不累计
