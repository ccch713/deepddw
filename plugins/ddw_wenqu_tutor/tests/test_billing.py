"""钱包对接测试（成功/余额不足/幂等）。"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plugins.ddw_wenqu_tutor.services.session import (
    end_session,
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
def mock_wallet_success():
    """Mock 钱包成功扣费。"""
    client = AsyncMock()
    client.charge = AsyncMock(
        return_value={
            "txn_no": "TXN_SUCCESS_001",
            "balance_after_cents": 8000,
        }
    )
    return client


@pytest.fixture
def mock_wallet_402():
    """Mock 钱包余额不足。"""
    client = AsyncMock()
    client.charge = AsyncMock(
        side_effect=Exception(
            '{"status":402,"detail":"余额不足"}'
        )
    )
    return client


@pytest.fixture
def active_session():
    """活跃会话。"""
    session = MagicMock()
    session.id = "WS_BILLING_TEST"
    session.student_name = "CXY"
    session.subject = "physics"
    session.status = "active"
    session.active_seconds = 1800  # 30 分钟
    return session


@pytest.mark.asyncio
async def test_billing_success(
    mock_db, mock_wallet_success, active_session
):
    """扣费成功。"""
    with patch(
        "plugins.ddw_wenqu_tutor.services.session.get_session",
        return_value=active_session,
    ):
        result = await end_session(
            mock_db,
            "WS_BILLING_TEST",
            mock_wallet_success,
        )

        assert result["active_minutes"] == 30
        # M0-5 用量计费：无消息会话 → 最低 1 分（原 30×1200=36000 已弃用）
        assert result["charge_cents"] == 1
        assert result["txn_no"] == "TXN_SUCCESS_001"
        assert result["balance_after_cents"] == 8000

        # 验证钱包被正确调用
        mock_wallet_success.charge.assert_called_once_with(
            user_id="CXY",
            charge_type="study_time",
            subject="physics",
            ref_id="WS_BILLING_TEST",
            ref_type="session",
            amount_cents=1,
        )


@pytest.mark.asyncio
async def test_billing_402_graceful(
    mock_db, mock_wallet_402, active_session
):
    """余额不足 → 抛出 ValueError（不静默），错误事件记录，会话保持可重试。"""
    with patch(
        "plugins.ddw_wenqu_tutor.services.session.get_session",
        return_value=active_session,
    ):
        with pytest.raises(ValueError, match="wallet charge failed"):
            await end_session(
                mock_db,
                "WS_BILLING_TEST",
                mock_wallet_402,
            )

        # 验证错误事件被记录
        error_events = [
            call
            for call in mock_db.add.call_args_list
            if hasattr(call[0][0], "event_type")
            and call[0][0].event_type == "charge_error"
        ]
        assert len(error_events) == 1


@pytest.mark.asyncio
async def test_billing_idempotent(
    mock_db, mock_wallet_success, active_session
):
    """幂等：重复 end 不重复扣费。"""
    with patch(
        "plugins.ddw_wenqu_tutor.services.session.get_session",
        return_value=active_session,
    ):
        # 第一次下课
        await end_session(
            mock_db,
            "WS_BILLING_TEST",
            mock_wallet_success,
        )

        # 模拟会话已 billed
        active_session.status = "billed"

        # 第二次下课应抛异常
        with pytest.raises(ValueError, match="already billed"):
            await end_session(
                mock_db,
                "WS_BILLING_TEST",
                mock_wallet_success,
            )

        # 钱包只被调用一次
        assert mock_wallet_success.charge.call_count == 1


@pytest.mark.asyncio
async def test_billing_active_minutes_round_up(
    mock_db, mock_wallet_success, active_session
):
    """活跃分钟向上取整。"""
    # 61 秒 → 2 分钟
    active_session.active_seconds = 61

    with patch(
        "plugins.ddw_wenqu_tutor.services.session.get_session",
        return_value=active_session,
    ):
        result = await end_session(
            mock_db,
            "WS_BILLING_TEST",
            mock_wallet_success,
        )

        assert result["active_minutes"] == 2
        # M0-5 用量计费：无消息会话 → 最低 1 分（原 2×1200=2400 已弃用）
        assert result["charge_cents"] == 1


@pytest.mark.asyncio
async def test_billing_minimum_one_minute(
    mock_db, mock_wallet_success, active_session
):
    """最少 1 分钟。"""
    active_session.active_seconds = 10  # 10 秒

    with patch(
        "plugins.ddw_wenqu_tutor.services.session.get_session",
        return_value=active_session,
    ):
        result = await end_session(
            mock_db,
            "WS_BILLING_TEST",
            mock_wallet_success,
        )

        assert result["active_minutes"] == 1
        # M0-5 用量计费：无消息会话 → 最低 1 分（原 1×1200=1200 已弃用）
        assert result["charge_cents"] == 1


@pytest.mark.asyncio
async def test_billing_session_not_found(mock_db):
    """会话不存在。"""
    with patch(
        "plugins.ddw_wenqu_tutor.services.session.get_session",
        return_value=None,
    ):
        with pytest.raises(
            ValueError, match="not found"
        ):
            await end_session(
                mock_db, "WS_NOT_EXIST", AsyncMock()
            )


@pytest.mark.asyncio
async def test_billing_wallet_exception_logged(
    mock_db, active_session
):
    """钱包异常被记录。"""
    # 钱包抛出非 402 异常
    client = AsyncMock()
    client.charge = AsyncMock(
        side_effect=Exception("网络超时")
    )

    with patch(
        "plugins.ddw_wenqu_tutor.services.session.get_session",
        return_value=active_session,
    ):
        with pytest.raises(ValueError, match="wallet charge failed"):
            await end_session(
                mock_db, "WS_BILLING_TEST", client
            )

        # 异常不再静默：会话保持 active 可重试，错误事件被记录
        from unittest.mock import ANY

        mock_db.add.assert_any_call(
            ANY  # WenquStudyEvent(charge_error)
        )
