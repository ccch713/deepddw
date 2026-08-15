"""按量扣费服务 — 幂等键 + 乐观锁扣减 + 混合扣费 + 平台抽佣。"""
from __future__ import annotations

import logging
import os
import random
import time
from typing import Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wallet.models import ChargeRecord
from plugins.ddw_wallet.schemas import ChargeOut
from plugins.ddw_wallet.services.account import (
    InsufficientBalanceError,
    debit_balance,
)

logger = logging.getLogger(__name__)

PLATFORM_FEE_PERCENT = int(os.getenv("DDW_WALLET_PLATFORM_FEE_PERCENT", "5"))


def _gen_txn_no() -> str:
    """生成扣费流水号：C + 时间戳 + 随机4位。"""
    ts = time.strftime("%Y%m%d%H%M%S")
    rand = f"{random.randint(0, 9999):04d}"
    return f"C{ts}{rand}"


async def charge(
    session: AsyncSession,
    user_id: str,
    charge_type: str,
    subject: str | None,
    ref_id: str,
    ref_type: str,
    amount_cents: int,
    tenant_id: str = "default",
) -> ChargeOut:
    """按量扣费（幂等，默认扣 recharge 钱包）。

    同一 ref_id 只扣一次，返回首次流水。
    余额不足抛 InsufficientBalanceError。
    """
    # 幂等检查
    stmt = select(ChargeRecord).where(
        ChargeRecord.ref_id == ref_id
    )
    result = await session.execute(stmt)
    existed = result.scalar_one_or_none()
    if existed is not None:
        logger.info(
            "Charge idempotent hit: ref_id=%s txn=%s",
            ref_id, existed.txn_no,
        )
        return ChargeOut(
            txn_no=existed.txn_no,
            amount_cents=existed.amount_cents,
            balance_after=existed.balance_after,
        )

    # 扣费（默认 recharge）
    bal_result = await debit_balance(
        session, user_id, amount_cents
    )

    # 记录流水
    txn_no = _gen_txn_no()
    rec = ChargeRecord(
        txn_no=txn_no,
        user_id=user_id,
        tenant_id=tenant_id,
        amount_cents=amount_cents,
        charge_type=charge_type,
        subject=subject,
        ref_id=ref_id,
        ref_type=ref_type,
        balance_after=bal_result.balance_cents,
    )
    session.add(rec)
    await session.flush()

    logger.info(
        "Charged %d from user %s, txn %s, bal %d",
        amount_cents, user_id, txn_no,
        bal_result.balance_cents,
    )
    return ChargeOut(
        txn_no=txn_no,
        amount_cents=amount_cents,
        balance_after=bal_result.balance_cents,
    )


async def charge_with_fallback(
    session: AsyncSession,
    user_id: str,
    amount_cents: int,
    ref_id: str,
    charge_type: str,
    tenant_id: str = "default",
    subject: str | None = None,
    ref_type: str = "session",
    priority: Tuple[str, ...] = ("recharge", "income", "skin"),
) -> ChargeOut:
    """混合扣费（三钱包优先级链）。

    按 priority 逐钱包扣减，任一扣成功即返回。
    全部不足 → InsufficientBalanceError(402)。

    Args:
        priority: 钱包优先级（默认 recharge→income→skin）
    """
    # 幂等检查
    stmt = select(ChargeRecord).where(
        ChargeRecord.ref_id == ref_id
    )
    result = await session.execute(stmt)
    existed = result.scalar_one_or_none()
    if existed is not None:
        logger.info(
            "Charge with fallback idempotent hit: ref_id=%s", ref_id
        )
        return ChargeOut(
            txn_no=existed.txn_no,
            amount_cents=existed.amount_cents,
            balance_after=existed.balance_after,
        )

    last_error = None
    for target in priority:
        try:
            bal_result = await debit_balance(
                session, user_id, amount_cents, target=target
            )
            # 记录流水（标注 balance_type）
            txn_no = _gen_txn_no()
            rec = ChargeRecord(
                txn_no=txn_no,
                user_id=user_id,
                tenant_id=tenant_id,
                amount_cents=amount_cents,
                charge_type=charge_type,
                subject=subject,
                ref_id=ref_id,
                ref_type=ref_type,
                balance_after=bal_result.balance_cents,
            )
            session.add(rec)
            await session.flush()

            logger.info(
                "Charge with fallback %d from %s %s, txn %s, bal %d",
                amount_cents, user_id, target, txn_no,
                bal_result.balance_cents,
            )
            return ChargeOut(
                txn_no=txn_no,
                amount_cents=amount_cents,
                balance_after=bal_result.balance_cents,
            )
        except InsufficientBalanceError as exc:
            last_error = exc
            logger.info(
                "Wallet %s insufficient for user %s (have %d, need %d), trying next",
                target, user_id, exc.balance_cents, exc.required_cents,
            )
            continue

    # 所有钱包都不足
    raise InsufficientBalanceError(
        balance_cents=last_error.balance_cents if last_error else 0,
        required_cents=amount_cents,
    )


async def settle_platform_fee(
    session: AsyncSession,
    txn_no: str,
    amount_cents: int,
) -> int:
    """平台抽佣（默认 5%，可配置 DDW_WALLET_PLATFORM_FEE_PERCENT）。

    从消费金额中抽取平台服务费，写入 charge_records（type=platform_fee）。
    幂等：同 txn_no 只抽一次。

    Returns:
        抽佣金额（分）
    """
    # 幂等检查
    stmt = select(ChargeRecord).where(
        ChargeRecord.ref_id == f"PF_{txn_no}"
    )
    result = await session.execute(stmt)
    existed = result.scalar_one_or_none()
    if existed is not None:
        logger.info("Platform fee idempotent hit: %s", txn_no)
        return existed.amount_cents

    fee_cents = amount_cents * PLATFORM_FEE_PERCENT // 100
    if fee_cents <= 0:
        return 0

    fee_txn_no = f"PF{txn_no[1:]}"  # 复用时间戳
    rec = ChargeRecord(
        txn_no=fee_txn_no,
        user_id="platform",
        tenant_id="default",
        amount_cents=fee_cents,
        charge_type="platform_fee",
        subject=f"platform_fee_{PLATFORM_FEE_PERCENT}%",
        ref_id=f"PF_{txn_no}",
        ref_type="platform_fee",
        balance_after=0,
    )
    session.add(rec)
    await session.flush()

    logger.info(
        "Platform fee %d (%d%% of %d) from txn %s",
        fee_cents, PLATFORM_FEE_PERCENT, amount_cents, txn_no,
    )
    return fee_cents


__all__ = ["charge", "charge_with_fallback", "settle_platform_fee"]
