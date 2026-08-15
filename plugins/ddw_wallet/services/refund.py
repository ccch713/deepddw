"""退款服务 — 余额原路退回 + 真实退款调用。"""
from __future__ import annotations

import logging
import random
import time
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wallet.models import (
    RechargeOrder,
    RefundRecord,
)
from plugins.ddw_wallet.schemas import RefundOut
from plugins.ddw_wallet.services.account import debit_balance

logger = logging.getLogger(__name__)


def _gen_refund_no() -> str:
    """生成退款单号：F + 时间戳 + 随机4位。"""
    ts = time.strftime("%Y%m%d%H%M%S")
    rand = f"{random.randint(0, 9999):04d}"
    return f"F{ts}{rand}"


async def refund_balance(
    session: AsyncSession,
    user_id: str,
    amount_cents: int,
    tenant_id: str = "default",
    source: Literal["recharge", "income"] = "recharge",
) -> RefundOut:
    """余额退款（原路退回）。

    优先退最近一笔充值单（原路退回原则）。
    无充值记录则抛异常。
    """
    # 查找最近一笔已支付的充值单
    stmt = (
        select(RechargeOrder)
        .where(
            RechargeOrder.user_id == user_id,
            RechargeOrder.status == "paid",
        )
        .order_by(RechargeOrder.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()
    if order is None:
        raise ValueError(
            "No recharge record for refund"
        )

    # 扣余额（recharge 钱包）
    await debit_balance(session, user_id, amount_cents, target=source)

    # 创建退款记录
    refund_no = _gen_refund_no()
    rec = RefundRecord(
        refund_no=refund_no,
        user_id=user_id,
        tenant_id=tenant_id,
        amount_cents=amount_cents,
        channel=order.channel,
        source=source,
        status="processing",
    )
    session.add(rec)
    await session.flush()

    # 真实退款调用（不阻塞主流程，失败标记 failed）
    try:
        if order.channel == "wechat":
            from plugins.ddw_wallet.services.wechat_pay import (
                create_refund,
            )
            result = create_refund(
                order.order_no, refund_no, order.amount_cents, amount_cents
            )
            logger.info(
                "Wechat refund %s initiated: %s", refund_no, result
            )
        elif order.channel == "alipay":
            from plugins.ddw_wallet.services.alipay_client import (
                create_refund,
            )
            result = create_refund(
                order.order_no, refund_no, amount_cents
            )
            logger.info(
                "Alipay refund %s initiated: %s", refund_no, result
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Refund %s provider call failed: %s", refund_no, exc
        )
        # 不回滚本地记录，标记 failed 以便后续处理
        rec.status = "failed"
        await session.flush()

    logger.info(
        "Refund %s: user %s, amount %d, channel %s",
        refund_no, user_id, amount_cents, order.channel,
    )
    return RefundOut(
        refund_no=refund_no, status=rec.status
    )


async def handle_refund_notify(
    session: AsyncSession,
    refund_no: str,
    provider_refund_id: str,
    status: Literal["success", "failed"],
) -> bool:
    """退款回调处理（幂等）。

    Args:
        refund_no: 退款单号
        provider_refund_id: 微信/支付宝退款单号
        status: 成功/失败

    Returns:
        是否处理成功
    """
    # 查询退款记录
    stmt = select(RefundRecord).where(
        RefundRecord.refund_no == refund_no
    )
    result = await session.execute(stmt)
    rec = result.scalar_one_or_none()
    if rec is None:
        logger.warning("Refund not found: %s", refund_no)
        return False

    # 幂等：已处理直接返回
    if rec.status in ("success", "failed"):
        logger.info("Refund %s already %s", refund_no, rec.status)
        return True

    if status == "success":
        rec.status = "success"
        rec.provider_refund_id = provider_refund_id
    else:
        rec.status = "failed"
        rec.provider_refund_id = provider_refund_id

    await session.flush()
    logger.info(
        "Refund %s notified: %s, provider_id: %s",
        refund_no, status, provider_refund_id,
    )
    return True


__all__ = ["handle_refund_notify", "refund_balance"]
