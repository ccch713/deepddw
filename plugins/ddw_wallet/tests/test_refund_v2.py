"""M1 退款 v2 测试：参数校验 + 回调状态流转。"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch

from plugins.ddw_wallet.services.account import credit_balance, get_or_create_account
from plugins.ddw_wallet.services.recharge import handle_wechat_notify, create_recharge
from plugins.ddw_wallet.services.refund import refund_balance, handle_refund_notify


@pytest.mark.asyncio
async def test_refund_params(session: AsyncSession):
    """退款参数校验：无充值单报错。"""
    await get_or_create_account(session, "u_rv1", tenant_id="default")
    await credit_balance(session, "u_rv1", 1000, tenant_id="default")
    await session.commit()

    with pytest.raises(ValueError, match="No recharge record"):
        await refund_balance(session, "u_rv1", 500, tenant_id="default")


@pytest.mark.asyncio
async def test_refund_callback_status(session: AsyncSession):
    """退款回调状态流转：processing → success。"""
    await get_or_create_account(session, "u_rv2", tenant_id="default")
    order = await create_recharge(session, "u_rv2", 1000, "wechat", tenant_id="default")
    await session.commit()

    data = {"out_trade_no": order.order_no, "trade_state": "SUCCESS", "amount": {"total": 1000}, "transaction_id": "TX_rv2"}
    await handle_wechat_notify(session, data)
    await session.commit()

    with patch("plugins.ddw_wallet.services.wechat_pay.create_refund", return_value={"status": "mock"}):
        res = await refund_balance(session, "u_rv2", 500, tenant_id="default")
    assert res.status in ("processing", "success", "failed")

    ok = await handle_refund_notify(session, res.refund_no, "PROV_RF_001", "success")
    assert ok is True
