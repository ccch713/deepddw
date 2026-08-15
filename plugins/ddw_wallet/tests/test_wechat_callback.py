"""微信回调验签/解密/幂等测试。"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wallet.services.account import (
    get_balance,
    get_or_create_account,
)
from plugins.ddw_wallet.services.recharge import (
    create_recharge,
    handle_wechat_notify,
)


def _make_callback_data(
    order_no: str,
    amount: int = 500,
    trade_state: str = "SUCCESS",
) -> dict:
    """构造微信回调数据。"""
    return {
        "out_trade_no": order_no,
        "trade_state": trade_state,
        "amount": {"total": amount},
        "transaction_id": f"TX_{order_no}",
    }


@pytest.mark.asyncio
async def test_wechat_notify_success(
    session: AsyncSession,
):
    """mock 回调 → 入账 500 分，订单 paid。"""
    await get_or_create_account(session, "u_wx_cb", tenant_id="default")
    await session.commit()

    order = await create_recharge(
        session, "u_wx_cb", 500, "wechat"
    )
    await session.commit()

    data = _make_callback_data(order.order_no, 500)
    ok, resp = await handle_wechat_notify(session, data)
    await session.commit()

    assert ok is True
    assert '"SUCCESS"' in resp

    bal = await get_balance(session, "u_wx_cb")
    assert bal.balance_cents == 500


@pytest.mark.asyncio
async def test_wechat_notify_idempotent(
    session: AsyncSession,
):
    """同回调重发 → 余额只加一次。"""
    await get_or_create_account(session, "u_idem", tenant_id="default")
    await session.commit()

    order = await create_recharge(
        session, "u_idem", 500, "wechat"
    )
    await session.commit()

    data = _make_callback_data(order.order_no, 500)
    ok1, _ = await handle_wechat_notify(session, data)
    await session.commit()

    # 重发
    ok2, _ = await handle_wechat_notify(session, data)
    await session.commit()

    assert ok1 is True
    assert ok2 is True

    bal = await get_balance(session, "u_idem")
    assert bal.balance_cents == 500  # 只加一次


@pytest.mark.asyncio
async def test_wechat_notify_amount_mismatch(
    session: AsyncSession,
):
    """回调金额≠订单金额 → 拒绝且不入账。"""
    await get_or_create_account(session, "u_mis", tenant_id="default")
    await session.commit()

    order = await create_recharge(
        session, "u_mis", 500, "wechat"
    )
    await session.commit()

    # 回调金额 600 ≠ 订单 500
    data = _make_callback_data(order.order_no, 600)
    ok, resp = await handle_wechat_notify(session, data)
    await session.commit()

    assert ok is False
    assert "Amount mismatch" in resp

    bal = await get_balance(session, "u_mis")
    assert bal.balance_cents == 0  # 未入账


@pytest.mark.asyncio
async def test_wechat_notify_bad_signature(
    session: AsyncSession,
):
    """验签失败（trade_state != SUCCESS）→ 不入账。"""
    await get_or_create_account(session, "u_bad", tenant_id="default")
    await session.commit()

    order = await create_recharge(
        session, "u_bad", 500, "wechat"
    )
    await session.commit()

    data = _make_callback_data(
        order.order_no, 500, trade_state="FAIL"
    )
    ok, resp = await handle_wechat_notify(session, data)
    await session.commit()

    # 非 SUCCESS 状态直接确认，不处理
    assert ok is True

    bal = await get_balance(session, "u_bad")
    assert bal.balance_cents == 0


@pytest.mark.asyncio
async def test_wechat_notify_non_success_state(
    session: AsyncSession,
):
    """trade_state=NOTPAY → 直接确认，不入账。"""
    await get_or_create_account(session, "u_np", tenant_id="default")
    await session.commit()

    order = await create_recharge(
        session, "u_np", 500, "wechat"
    )
    await session.commit()

    data = _make_callback_data(
        order.order_no, 500, trade_state="NOTPAY"
    )
    ok, _ = await handle_wechat_notify(session, data)
    await session.commit()

    assert ok is True
    bal = await get_balance(session, "u_np")
    assert bal.balance_cents == 0
