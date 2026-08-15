"""退款测试。"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wallet.services.account import (
    InsufficientBalanceError,
    credit_balance,
    get_balance,
    get_or_create_account,
)
from plugins.ddw_wallet.services.recharge import (
    create_recharge,
    handle_wechat_notify,
)
from plugins.ddw_wallet.services.refund import (
    refund_balance,
)


@pytest.mark.asyncio
async def test_refund_balance(session: AsyncSession):
    """退款 → 余额减少，RefundRecord processing。"""
    # 创建账户
    await get_or_create_account(session, "u_rf1", tenant_id="default")
    await session.commit()

    # 充值并入账
    order = await create_recharge(
        session, "u_rf1", 1000, "wechat"
    )
    await session.commit()

    data = {
        "out_trade_no": order.order_no,
        "trade_state": "SUCCESS",
        "amount": {"total": 1000},
        "transaction_id": "TX_rf1",
    }
    await handle_wechat_notify(session, data)
    await session.commit()

    # 退款 500 分（mock wechat_pay.create_refund 避免真实调用）
    from unittest.mock import patch
    with patch("plugins.ddw_wallet.services.wechat_pay.create_refund", return_value={"status": "mock"}):
        res = await refund_balance(
            session, "u_rf1", 500
        )
    await session.commit()

    assert res.status == "processing"
    assert res.refund_no.startswith("F")

    bal = await get_balance(session, "u_rf1")
    assert bal.balance_cents == 500


@pytest.mark.asyncio
async def test_refund_no_recharge(session: AsyncSession):
    """无充值记录 → 抛异常。"""
    await get_or_create_account(session, "u_rf2", tenant_id="default")
    await session.commit()

    await credit_balance(session, "u_rf2", 500, tenant_id="default")

    with pytest.raises(
        ValueError, match="No recharge record"
    ):
        await refund_balance(session, "u_rf2", 200)


@pytest.mark.asyncio
async def test_refund_insufficient(session: AsyncSession):
    """退款金额 > 余额 → InsufficientBalanceError。"""
    await get_or_create_account(session, "u_rf3", tenant_id="default")
    await session.commit()

    order = await create_recharge(
        session, "u_rf3", 500, "wechat"
    )
    await session.commit()

    data = {
        "out_trade_no": order.order_no,
        "trade_state": "SUCCESS",
        "amount": {"total": 500},
        "transaction_id": "TX_rf3",
    }
    await handle_wechat_notify(session, data)
    await session.commit()

    with pytest.raises(InsufficientBalanceError):
        await refund_balance(session, "u_rf3", 1000)
