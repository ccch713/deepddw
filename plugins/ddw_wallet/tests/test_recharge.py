"""充值单创建测试。"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wallet.schemas import RechargeOut
from plugins.ddw_wallet.services.account import (
    get_or_create_account,
)
from plugins.ddw_wallet.services.recharge import (
    create_recharge,
    get_recharge_order,
)


@pytest.mark.asyncio
async def test_create_wechat_recharge(
    session: AsyncSession,
):
    """充值 500 分 → 返回 code_url，订单 pending。"""
    await get_or_create_account(session, "u_wx", tenant_id="default")
    await session.commit()

    res = await create_recharge(
        session, "u_wx", 500, "wechat"
    )
    await session.commit()

    assert isinstance(res, RechargeOut)
    assert res.amount_cents == 500
    assert res.channel == "wechat"
    assert res.status == "pending"
    assert res.pay_params is not None
    assert "code_url" in res.pay_params


@pytest.mark.asyncio
async def test_create_alipay_recharge(
    session: AsyncSession,
):
    """支付宝充值 → 返回 form_html。"""
    await get_or_create_account(session, "u_ali", tenant_id="default")
    await session.commit()

    res = await create_recharge(
        session, "u_ali", 1000, "alipay"
    )
    await session.commit()

    assert res.channel == "alipay"
    assert res.pay_params is not None
    assert "form_html" in res.pay_params


@pytest.mark.asyncio
async def test_recharge_min_amount():
    """充值 < 100 分（<1 元）→ Pydantic 校验错误（config min_recharge_cents=100）。"""
    from pydantic import ValidationError

    from plugins.ddw_wallet.schemas import RechargeCreate

    with pytest.raises(ValidationError):
        RechargeCreate(
            amount_cents=50,  # < 100 分（1 元）= config.min_recharge_cents
            channel="wechat",
            user_id="u_min",
        )


@pytest.mark.asyncio
async def test_get_recharge_order(session: AsyncSession):
    """查询充值单。"""
    await get_or_create_account(session, "u_qry", tenant_id="default")
    await session.commit()

    created = await create_recharge(
        session, "u_qry", 500, "wechat"
    )
    await session.commit()

    order = await get_recharge_order(
        session, created.order_no
    )
    assert order is not None
    assert order.status == "pending"
    assert order.amount_cents == 500
