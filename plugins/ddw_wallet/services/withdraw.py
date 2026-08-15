"""提现申请服务（G15）— income 余额可提现。"""
from __future__ import annotations

import logging
import random
import time

from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wallet.models import WithdrawRequest
from plugins.ddw_wallet.services.account import (
    debit_balance,
)

logger = logging.getLogger(__name__)

MIN_WITHDRAW_CENTS = 1000  # 最低提现 ¥10


def _gen_withdraw_no() -> str:
    ts = time.strftime("%Y%m%d%H%M%S")
    rand = f"{random.randint(0, 9999):04d}"
    return f"W{ts}{rand}"


async def create_withdraw(
    session: AsyncSession,
    user_id: str,
    amount_cents: int,
    channel: str = "wechat",
    tenant_id: str = "default",
) -> WithdrawRequest:
    """创建提现申请（从 income 余额扣减）。

    Raises:
        ValueError: 金额不足最低提现
        InsufficientBalanceError: income 余额不足
    """
    if amount_cents < MIN_WITHDRAW_CENTS:
        raise ValueError(f"最低提现 ¥{MIN_WITHDRAW_CENTS / 100:.0f}")

    # 从 income 余额扣减
    await debit_balance(session, user_id, amount_cents, target="income", tenant_id=tenant_id)

    withdraw_no = _gen_withdraw_no()
    withdraw_no = _gen_withdraw_no()
    rec = WithdrawRequest(
        withdraw_no=withdraw_no,
        tenant_id=tenant_id,
        user_id=user_id,
        amount_cents=amount_cents,
        channel=channel,
        status="pending",
    )
    session.add(rec)
    await session.flush()
    logger.info("Withdraw %s: user %s, amount %d", withdraw_no, user_id, amount_cents)
    return rec
