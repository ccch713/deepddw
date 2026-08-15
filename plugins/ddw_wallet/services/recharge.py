"""充值服务 — 充值单创建 + 回调入账（幂等）。"""
from __future__ import annotations

import json
import logging
import random
import time
from datetime import datetime
from decimal import Decimal
from typing import Tuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wallet.models import RechargeOrder
from plugins.ddw_wallet.schemas import RechargeOut
from plugins.ddw_wallet.services.account import credit_balance

logger = logging.getLogger(__name__)


def _gen_order_no() -> str:
    """生成平台单号：WQ + 时间戳 + 随机4位。"""
    ts = time.strftime("%Y%m%d%H%M%S")
    rand = f"{random.randint(0, 9999):04d}"
    return f"WQ{ts}{rand}"


async def create_recharge(
    session: AsyncSession,
    user_id: str,
    amount_cents: int,
    channel: str,
    tenant_id: str = "default",
) -> RechargeOut:
    """创建充值单。

    Returns:
        RechargeOut with pay_params for wechat (code_url)
        or alipay (form_html placeholder).
    """
    order_no = _gen_order_no()
    order = RechargeOrder(
        order_no=order_no,
        user_id=user_id,
        tenant_id=tenant_id,
        amount_cents=amount_cents,
        channel=channel,
        status="pending",
    )
    session.add(order)
    await session.flush()

    pay_params = None
    if channel == "wechat":
        try:
            from plugins.ddw_wallet.services.wechat_pay import (
                create_native_order,
            )
            code_url = create_native_order(
                order_no, amount_cents, "DDW 预付费钱包充值"
            )
            pay_params = {"code_url": code_url}
            logger.info(
                "Wechat native order created: %s", order_no
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Wechat pay unavailable (%s), fallback to mock", exc
            )
            pay_params = {"code_url": f"weixin://wxpay/{order_no}"}
    elif channel == "alipay":
        pay_params = {
            "form_html": f"<form>alipay mock {order_no}</form>"
        }

    logger.info(
        "Created recharge order %s for user %s, "
        "amount %d, channel %s",
        order_no, user_id, amount_cents, channel,
    )
    return RechargeOut(
        order_no=order_no,
        amount_cents=amount_cents,
        channel=channel,
        status="pending",
        pay_params=pay_params,
    )


async def handle_wechat_notify(
    session: AsyncSession,
    data: dict,
) -> Tuple[bool, str]:
    """处理微信支付回调（幂等）。

    Args:
        session: DB session
        data: 解密后的回调数据
              {out_trade_no, trade_state, amount, transaction_id}

    Returns:
        (是否成功应答, 应答文本)
    """
    # SDK callback 返回嵌套结构（resource 内为交易数据），兼容展平两种
    payload = data.get("resource") or data
    if payload.get("trade_state") != "SUCCESS":
        return True, '{"code":"SUCCESS","message":"OK"}'

    out_trade_no = payload["out_trade_no"]
    paid_amount = payload["amount"]["total"]
    transaction_id = payload["transaction_id"]

    # 使用原生 SQL 做 SELECT FOR UPDATE（幂等）
    row = await session.execute(
        text(
            "SELECT id, status, amount_cents, user_id "
            "FROM dw_wallet_recharge_orders "
            "WHERE order_no = :ono"
        ),
        {"ono": out_trade_no},
    )
    order_row = row.first()
    if order_row is None:
        return False, (
            '{"code":"FAIL","message":"Order not found"}'
        )

    if order_row.status == "paid":
        return True, '{"code":"SUCCESS","message":"OK"}'

    if order_row.status != "pending":
        return False, (
            '{"code":"FAIL","message":"Status error"}'
        )

    if paid_amount != order_row.amount_cents:
        return False, (
            '{"code":"FAIL","message":"Amount mismatch"}'
        )

    # 入账
    await session.execute(
        text(
            "UPDATE dw_wallet_recharge_orders "
            "SET status='paid', "
            "    provider_order_id=:tid, "
            "    notify_raw=:raw, "
            "    paid_at=:now "
            "WHERE order_no=:ono AND status='pending'"
        ),
        {
            "tid": transaction_id,
            "raw": json.dumps(payload, ensure_ascii=False),
            "now": datetime.now().isoformat(),
            "ono": out_trade_no,
        },
    )

    # 加余额
    await credit_balance(
        session, order_row.user_id, order_row.amount_cents
    )

    logger.info(
        "Wechat notify: order %s paid, amount %d",
        out_trade_no, paid_amount,
    )
    return True, '{"code":"SUCCESS","message":"OK"}'


async def handle_alipay_notify(
    session: AsyncSession,
    data: dict,
) -> Tuple[bool, str]:
    """处理支付宝异步通知（幂等）。

    Args:
        data: {out_trade_no, trade_status, total_amount, trade_no}

    Returns:
        (是否成功, 应答文本)
    """
    trade_status = data.get("trade_status", "")
    if trade_status not in ("TRADE_SUCCESS", "TRADE_FINISHED"):
        return True, "success"

    out_trade_no = data["out_trade_no"]
    # 金额铁律：整数分。支付宝 total_amount 为字符串元（如 "0.29"），
    # 必须用 Decimal 精确转换，禁止 float（float("0.29")*100=28.999... 丢 1 分）
    total_amount = int(Decimal(data.get("total_amount", "0")) * 100)
    trade_no = data.get("trade_no", "")

    row = await session.execute(
        text(
            "SELECT id, status, amount_cents, user_id "
            "FROM dw_wallet_recharge_orders "
            "WHERE order_no = :ono"
        ),
        {"ono": out_trade_no},
    )
    order_row = row.first()
    if order_row is None:
        return False, "fail"
    if order_row.status == "paid":
        return True, "success"
    if order_row.status != "pending":
        return False, "fail"
    if total_amount != order_row.amount_cents:
        return False, "fail"

    await session.execute(
        text(
            "UPDATE dw_wallet_recharge_orders "
            "SET status='paid', "
            "    provider_order_id=:tid, "
            "    notify_raw=:raw, "
            "    paid_at=:now "
            "WHERE order_no=:ono AND status='pending'"
        ),
        {
            "tid": trade_no,
            "raw": json.dumps(data, ensure_ascii=False),
            "now": datetime.now().isoformat(),
            "ono": out_trade_no,
        },
    )
    await credit_balance(
        session, order_row.user_id, order_row.amount_cents
    )

    logger.info(
        "Alipay notify: order %s paid, amount %d",
        out_trade_no, total_amount,
    )
    return True, "success"


async def get_recharge_order(
    session: AsyncSession,
    order_no: str,
) -> RechargeOrder | None:
    """查询充值单状态。"""
    stmt = select(RechargeOrder).where(
        RechargeOrder.order_no == order_no
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


__all__ = [
    "create_recharge",
    "get_recharge_order",
    "handle_alipay_notify",
    "handle_wechat_notify",
]
