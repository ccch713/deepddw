"""课件分成服务 — 80%/50% 学科规则。"""
from __future__ import annotations

import logging
import random
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wallet.models import (
    RoyaltyRecord,
    WalletAccount,
)
from plugins.ddw_wallet.schemas import RoyaltyOut
from plugins.ddw_wallet.services.account import (
    credit_balance,
)

logger = logging.getLogger(__name__)

# 学科分成规则：英语=50%，其他=80%
SUBJECT_ROYALTY_RATE: dict[str, int] = {
    "default": 80,
    "english": 50,
}


def _gen_royalty_no() -> str:
    """生成分成单号：R + 时间戳 + 随机4位。"""
    ts = time.strftime("%Y%m%d%H%M%S")
    rand = f"{random.randint(0, 9999):04d}"
    return f"R{ts}{rand}"


async def settle_royalty(
    session: AsyncSession,
    author_user_id: str,
    courseware_id: str,
    trigger_txn_id: str,
    study_amount_cents: int,
    subject: str | None,
    tenant_id: str = "default",
) -> RoyaltyOut:
    """课件分成入账（幂等）。

    同一 trigger_txn_id 只分一次。
    英语=50%，其他=80%。
    """
    # 幂等检查
    stmt = select(RoyaltyRecord).where(
        RoyaltyRecord.trigger_txn_id == trigger_txn_id
    )
    result = await session.execute(stmt)
    existed = result.scalar_one_or_none()
    if existed is not None:
        logger.info(
            "Royalty idempotent hit: trigger=%s",
            trigger_txn_id,
        )
        return RoyaltyOut(
            royalty_no=existed.royalty_no,
            income_cents=existed.income_cents,
        )

    # 确定分成比例
    rate = SUBJECT_ROYALTY_RATE.get(
        subject or "default",
        SUBJECT_ROYALTY_RATE["default"],
    )
    income = study_amount_cents * rate // 100
    if income <= 0:
        raise ValueError("Royalty income is zero")

    # 确保作者账户存在
    acc_stmt = select(WalletAccount).where(
        WalletAccount.user_id == author_user_id
    )
    acc_result = await session.execute(acc_stmt)
    acc = acc_result.scalar_one_or_none()
    if acc is None:
        # 自动创建作者账户
        from plugins.ddw_wallet.services.account import (
            get_or_create_account,
        )
        await get_or_create_account(
            session, author_user_id
        )

    # 加余额
    await credit_balance(
        session, author_user_id, income
    )

    # 记录分成
    royalty_no = _gen_royalty_no()
    rec = RoyaltyRecord(
        royalty_no=royalty_no,
        author_user_id=author_user_id,
        tenant_id=tenant_id,
        courseware_id=courseware_id,
        trigger_txn_id=trigger_txn_id,
        study_amount_cents=study_amount_cents,
        rate_percent=rate,
        income_cents=income,
        status="settled",
    )
    session.add(rec)
    await session.flush()

    logger.info(
        "Royalty %s: author %s, rate %d%%, "
        "income %d, trigger %s",
        royalty_no, author_user_id, rate,
        income, trigger_txn_id,
    )
    return RoyaltyOut(
        royalty_no=royalty_no, income_cents=income
    )


__all__ = [
    "SUBJECT_ROYALTY_RATE",
    "settle_royalty",
]
