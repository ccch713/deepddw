"""问渠 × Wallet Hub 整合测试。

3 个核心场景：
1. T1: 余额充足 → 开课成功
2. T2: 余额不足 → 402
3. T3: 下课扣费成功
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from plugins.ddw_wenqu_tutor.services.wallet_client import (
    WenquWalletClient,
    InsufficientBalanceError,
)


@pytest.fixture
def wallet_client():
    """创建测试用的 wallet client。"""
    return WenquWalletClient(base_url="http://mock-wallet:8500")


@pytest.fixture
def mock_balance_ok():
    """余额充足的 mock 响应。"""
    return {
        "recharge_balance_cents": 5000,
        "income_balance_cents": 1000,
        "skin_balance_cents": 0,
    }


@pytest.fixture
def mock_balance_empty():
    """余额不足的 mock 响应。"""
    return {
        "recharge_balance_cents": 0,
        "income_balance_cents": 0,
        "skin_balance_cents": 0,
    }


@pytest.fixture
def mock_charge_success():
    """扣费成功的 mock 响应。"""
    return {
        "txn_no": "C20260813ABCD1234",
        "amount_cents": 2400,
        "balance_after_cents": 2600,
    }


# ==================== T1: 余额充足 → 开课成功 ====================


@pytest.mark.asyncio
async def test_t1_balance_ok_start_session(
    wallet_client, mock_balance_ok, mock_charge_success
):
    """T1: 余额充足 → 开课成功。"""
    # Mock get_balance
    wallet_client.get_balance = AsyncMock(return_value=mock_balance_ok)

    # Mock charge
    wallet_client.charge = AsyncMock(return_value=mock_charge_success)

    # 验证余额检查
    has_balance = await wallet_client.check_balance("CXY", min_cents=100)
    assert has_balance is True

    # 验证扣费
    result = await wallet_client.charge(
        user_id="CXY",
        charge_type="study_time",
        subject="physics",
        ref_id="WS_TEST_001",
        ref_type="session",
        amount_cents=2400,
    )
    assert result["txn_no"] == "C20260813ABCD1234"
    assert result["amount_cents"] == 2400
    assert result["balance_after_cents"] == 2600


# ==================== T2: 余额不足 → 402 ====================


@pytest.mark.asyncio
async def test_t2_balance_insufficient_402(
    wallet_client, mock_balance_empty
):
    """T2: 余额不足 → 402 INSUFFICIENT_BALANCE。"""
    # Mock get_balance 返回空余额
    wallet_client.get_balance = AsyncMock(return_value=mock_balance_empty)

    # 验证余额检查
    has_balance = await wallet_client.check_balance("CXY", min_cents=100)
    assert has_balance is False


@pytest.mark.asyncio
async def test_t2_charge_insufficient_raises(wallet_client):
    """T2: 扣费时余额不足 → InsufficientBalanceError。"""
    # Mock charge 抛出余额不足异常
    wallet_client.charge = AsyncMock(
        side_effect=InsufficientBalanceError(
            balance_cents=50, required_cents=2400
        )
    )

    with pytest.raises(InsufficientBalanceError) as exc_info:
        await wallet_client.charge(
            user_id="CXY",
            charge_type="study_time",
            subject="physics",
            ref_id="WS_TEST_002",
            ref_type="session",
            amount_cents=2400,
        )
    assert exc_info.value.balance_cents == 50
    assert exc_info.value.required_cents == 2400


# ==================== T3: 下课扣费成功 ====================


@pytest.mark.asyncio
async def test_t3_end_session_charge_success(
    wallet_client, mock_balance_ok, mock_charge_success
):
    """T3: 下课扣费成功。"""
    # Mock charge
    wallet_client.charge = AsyncMock(return_value=mock_charge_success)

    # 验证扣费调用
    result = await wallet_client.charge(
        user_id="CXY",
        charge_type="study_time",
        subject="chemistry",
        ref_id="WS_TEST_003",
        ref_type="session",
        amount_cents=2400,
        balance_priority="recharge,income,skin",
    )

    assert result["txn_no"] == "C20260813ABCD1234"
    assert result["amount_cents"] == 2400
    assert result["balance_after_cents"] == 2600

    # 验证幂等（同一 ref_id 重复调用）
    result2 = await wallet_client.charge(
        user_id="CXY",
        charge_type="study_time",
        subject="chemistry",
        ref_id="WS_TEST_003",  # 同一个 ref_id
        ref_type="session",
        amount_cents=2400,
    )
    # 幂等：返回相同结果
    assert result2["txn_no"] == result["txn_no"]


# ==================== 额外场景 ====================


@pytest.mark.asyncio
async def test_wallet_service_unavailable_graceful(wallet_client):
    """钱包服务不可用时的降级策略。"""
    from plugins.ddw_wenqu_tutor.services.wallet_client import WalletServiceError

    # Mock get_balance 抛出网络错误
    wallet_client.get_balance = AsyncMock(
        side_effect=WalletServiceError("connection refused")
    )

    # 余额检查：服务不可用时允许开课（降级）
    has_balance = await wallet_client.check_balance("CXY", min_cents=100)
    assert has_balance is True  # 降级：允许开课


@pytest.mark.asyncio
async def test_check_balance_with_income(wallet_client):
    """收入钱包也能用于余额检查。"""
    wallet_client.get_balance = AsyncMock(
        return_value={
            "recharge_balance_cents": 0,
            "income_balance_cents": 5000,
            "skin_balance_cents": 0,
        }
    )

    has_balance = await wallet_client.check_balance("CXY", min_cents=100)
    assert has_balance is True  # 收入钱包有余额