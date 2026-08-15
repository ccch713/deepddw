"""账户服务 — 创建/余额查询/乐观锁扣减 + 三钱包。"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wallet.models import WalletAccount

logger = logging.getLogger(__name__)

MAX_RETRY = 5


@dataclass
class BalanceResult:
    """轻量余额结果（避免 ORM 状态冲突）。"""
    user_id: str
    balance_cents: int
    version: int


@dataclass
class ThreeBalances:
    """三钱包余额查询结果。"""
    user_id: str
    recharge_balance_cents: int
    income_balance_cents: int
    skin_balance_cents: int
    frozen_cents: int
    available_recharge: int
    available_income: int
    available_skin: int


def _gen_txn_no(prefix: str = "A") -> str:
    """生成流水号：前缀 + 时间戳 + 随机4位。"""
    ts = time.strftime("%Y%m%d%H%M%S")
    rand = f"{random.randint(0, 9999):04d}"
    return f"{prefix}{ts}{rand}"


async def get_or_create_account(
    session: AsyncSession,
    user_id: str,
    tenant_id: str = "default",
) -> WalletAccount:
    """获取或创建钱包账户（幂等，三钱包默认0）。"""
    stmt = select(WalletAccount).where(
        WalletAccount.user_id == user_id
    )
    result = await session.execute(stmt)
    acc = result.scalar_one_or_none()
    if acc is not None:
        return acc

    acc = WalletAccount(
        user_id=user_id,
        tenant_id=tenant_id,
        recharge_balance_cents=0,
        income_balance_cents=0,
        skin_balance_cents=0,
        frozen_cents=0,
        status="active",
        version=0,
    )
    session.add(acc)
    await session.flush()
    logger.info(
        "Created wallet account for user %s", user_id
    )
    return acc


async def get_balance(
    session: AsyncSession,
    user_id: str,
) -> BalanceResult:
    """查询余额（兼容旧接口，返回 recharge 余额）。"""
    stmt = select(WalletAccount).where(
        WalletAccount.user_id == user_id
    )
    result = await session.execute(stmt)
    acc = result.scalar_one_or_none()
    if acc is None:
        raise ValueError(f"Account not found: {user_id}")
    return BalanceResult(
        user_id=acc.user_id,
        balance_cents=acc.recharge_balance_cents,
        version=acc.version,
    )


async def get_three_balances(
    session: AsyncSession,
    user_id: str,
) -> ThreeBalances:
    """查询三钱包余额。"""
    stmt = select(WalletAccount).where(
        WalletAccount.user_id == user_id
    )
    result = await session.execute(stmt)
    acc = result.scalar_one_or_none()
    if acc is None:
        raise ValueError(f"Account not found: {user_id}")
    return ThreeBalances(
        user_id=acc.user_id,
        recharge_balance_cents=acc.recharge_balance_cents,
        income_balance_cents=acc.income_balance_cents,
        skin_balance_cents=acc.skin_balance_cents,
        frozen_cents=acc.frozen_cents,
        available_recharge=acc.recharge_balance_cents - acc.frozen_cents,
        available_income=acc.income_balance_cents,
        available_skin=acc.skin_balance_cents,
    )


async def credit_balance(
    session: AsyncSession,
    user_id: str,
    amount_cents: int,
    tenant_id: str = "default",
    target: Literal["recharge", "income", "skin"] = "recharge",
) -> BalanceResult:
    """乐观锁加余额（三钱包定向）。

    Args:
        target: 充值钱包类型（默认 recharge）
    """
    field_map = {
        "recharge": "recharge_balance_cents",
        "income": "income_balance_cents",
        "skin": "skin_balance_cents",
    }
    field = field_map[target]

    for attempt in range(MAX_RETRY):
        stmt = select(WalletAccount).where(
            WalletAccount.user_id == user_id
        )
        result = await session.execute(stmt)
        acc = result.scalar_one_or_none()
        if acc is None:
            raise ValueError(
                f"Account not found: {user_id}"
            )
        if acc.status != "active":
            raise ValueError(
                f"Account not active: {user_id}"
            )

        ver = acc.version
        old_bal = getattr(acc, field)
        new_bal = old_bal + amount_cents
        upd = await session.execute(
            text(
                "UPDATE dw_wallet_accounts "
                f"SET {field}=:b, version=:v "
                "WHERE user_id=:u AND version=:ov"
            ),
            {"b": new_bal, "v": ver + 1,
             "u": user_id, "ov": ver},
        )
        if upd.rowcount == 1:
            await session.commit()
            logger.info(
                "Credited %d to %s %s, bal %d",
                amount_cents, user_id, target, new_bal,
            )
            try:
                from plugins.ddw_wallet.services.audit import log_audit
                await log_audit(session, tenant_id, user_id, "system", f"credit_{target}", amount_cents, old_bal, new_bal, reason=f"credit {target}")
            except Exception:  # noqa: BLE001
                pass
            return BalanceResult(
                user_id, new_bal, ver + 1
            )
        session.expire_all()
        logger.warning(
            "Credit retry %d for %s", attempt + 1, user_id
        )
    raise RuntimeError("Concurrent modification")


async def debit_balance(
    session: AsyncSession,
    user_id: str,
    amount_cents: int,
    tenant_id: str = "default",
    target: Literal["recharge", "income", "skin"] = "recharge",
) -> BalanceResult:
    """乐观锁扣余额（三钱包定向）。

    Args:
        target: 扣减钱包类型（默认 recharge）

    Raises:
        InsufficientBalanceError: 该钱包余额不足（扣减后 available = balance - frozen < 0 时）
    """
    field_map = {
        "recharge": "recharge_balance_cents",
        "income": "income_balance_cents",
        "skin": "skin_balance_cents",
    }
    field = field_map[target]

    for attempt in range(MAX_RETRY):
        stmt = select(WalletAccount).where(
            WalletAccount.user_id == user_id
        )
        result = await session.execute(stmt)
        acc = result.scalar_one_or_none()
        if acc is None:
            raise ValueError(
                f"Account not found: {user_id}"
            )
        if acc.status != "active":
            raise ValueError(
                f"Account not active: {user_id}"
            )

        old_bal = getattr(acc, field)
        frozen = acc.frozen_cents
        available = old_bal - frozen if target == "recharge" else old_bal

        if available < amount_cents:
            raise InsufficientBalanceError(
                balance_cents=old_bal,
                required_cents=amount_cents,
            )

        ver = acc.version
        new_bal = old_bal - amount_cents
        upd = await session.execute(
            text(
                "UPDATE dw_wallet_accounts "
                f"SET {field}=:b, version=:v "
                "WHERE user_id=:u AND version=:ov"
            ),
            {"b": new_bal, "v": ver + 1,
             "u": user_id, "ov": ver},
        )
        if upd.rowcount == 1:
            await session.commit()
            logger.info(
                "Debited %d from %s %s, bal %d",
                amount_cents, user_id, target, new_bal,
            )
            try:
                from plugins.ddw_wallet.services.audit import log_audit
                await log_audit(session, tenant_id, user_id, "system", f"debit_{target}", amount_cents, old_bal, new_bal, reason=f"debit {target}")
            except Exception:  # noqa: BLE001
                pass
            return BalanceResult(
                user_id, new_bal, ver + 1
            )
        session.expire_all()
        logger.warning(
            "Debit retry %d for %s", attempt + 1, user_id
        )
    raise RuntimeError("Concurrent modification")


async def freeze_balance(
    session: AsyncSession,
    user_id: str,
    amount_cents: int,
    reason: str = "",
    tenant_id: str = "default",
) -> BalanceResult:
    """冻结余额（乐观锁）。

    冻结后 frozen_cents 增加，recharge_balance_cents 不变。
    消费时 available = balance - frozen。
    """
    for attempt in range(MAX_RETRY):
        stmt = select(WalletAccount).where(
            WalletAccount.user_id == user_id
        )
        result = await session.execute(stmt)
        acc = result.scalar_one_or_none()
        if acc is None:
            raise ValueError(
                f"Account not found: {user_id}"
            )
        available = acc.recharge_balance_cents - acc.frozen_cents
        if available < amount_cents:
            raise InsufficientBalanceError(
                balance_cents=available,
                required_cents=amount_cents,
            )

        ver = acc.version
        new_frozen = acc.frozen_cents + amount_cents
        upd = await session.execute(
            text(
                "UPDATE dw_wallet_accounts "
                "SET frozen_cents=:f, version=:v "
                "WHERE user_id=:u AND version=:ov"
            ),
            {"f": new_frozen, "v": ver + 1,
             "u": user_id, "ov": ver},
        )
        if upd.rowcount == 1:
            await session.commit()
            logger.info(
                "Froze %d for %s, reason: %s",
                amount_cents, user_id, reason,
            )
            try:
                from plugins.ddw_wallet.services.audit import log_audit
                await log_audit(session, tenant_id, user_id, "system", "freeze", amount_cents, acc.recharge_balance_cents, acc.recharge_balance_cents, reason=reason)
            except Exception as exc:  # noqa: BLE001
                logger.warning("audit freeze failed: %s", exc)
            return BalanceResult(
                user_id, acc.recharge_balance_cents, ver + 1
            )
        session.expire_all()
        logger.warning(
            "Freeze retry %d for %s", attempt + 1, user_id
        )
    raise RuntimeError("Concurrent modification")


async def unfreeze_balance(
    session: AsyncSession,
    user_id: str,
    amount_cents: int,
    reason: str = "",
    tenant_id: str = "default",
) -> BalanceResult:
    """解冻余额（乐观锁）。"""
    for attempt in range(MAX_RETRY):
        stmt = select(WalletAccount).where(
            WalletAccount.user_id == user_id
        )
        result = await session.execute(stmt)
        acc = result.scalar_one_or_none()
        if acc is None:
            raise ValueError(
                f"Account not found: {user_id}"
            )
        if acc.frozen_cents < amount_cents:
            raise ValueError(
                f"Cannot unfreeze {amount_cents} > frozen {acc.frozen_cents}"
            )

        ver = acc.version
        new_frozen = acc.frozen_cents - amount_cents
        upd = await session.execute(
            text(
                "UPDATE dw_wallet_accounts "
                "SET frozen_cents=:f, version=:v "
                "WHERE user_id=:u AND version=:ov"
            ),
            {"f": new_frozen, "v": ver + 1,
             "u": user_id, "ov": ver},
        )
        if upd.rowcount == 1:
            await session.commit()
            logger.info(
                "Unfroze %d for %s, reason: %s",
                amount_cents, user_id, reason,
            )
            try:
                from plugins.ddw_wallet.services.audit import log_audit
                await log_audit(session, tenant_id, user_id, "system", "unfreeze", amount_cents, acc.recharge_balance_cents, acc.recharge_balance_cents, reason=reason)
            except Exception as exc:  # noqa: BLE001
                logger.warning("audit unfreeze failed: %s", exc)
            return BalanceResult(
                user_id, acc.recharge_balance_cents, ver + 1
            )
        session.expire_all()
        logger.warning(
            "Unfreeze retry %d for %s", attempt + 1, user_id
        )
    raise RuntimeError("Concurrent modification")


class InsufficientBalanceError(Exception):
    """余额不足异常。"""

    def __init__(
        self, balance_cents: int, required_cents: int
    ) -> None:
        self.balance_cents = balance_cents
        self.required_cents = required_cents
        super().__init__(
            f"Insufficient balance: have {balance_cents}, "
            f"need {required_cents}"
        )


__all__ = [
    "BalanceResult",
    "InsufficientBalanceError",
    "ThreeBalances",
    "credit_balance",
    "debit_balance",
    "freeze_balance",
    "get_balance",
    "get_or_create_account",
    "get_three_balances",
    "unfreeze_balance",
]
