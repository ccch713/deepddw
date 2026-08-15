"""G8 余额冻结/解冻 + G12 审计日志测试。"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wallet.models import AuditLog
from plugins.ddw_wallet.services.account import (
    InsufficientBalanceError,
    credit_balance,
    debit_balance,
    freeze_balance,
    get_or_create_account,
    get_three_balances,
    unfreeze_balance,
)
from plugins.ddw_wallet.services.audit import log_audit


@pytest.mark.asyncio
async def test_freeze_balance(session: AsyncSession):
    """冻结余额后不可消费。"""
    await get_or_create_account(session, "u_fr1", tenant_id="default")
    await credit_balance(session, "u_fr1", 1000, tenant_id="default")
    await session.commit()

    # 冻结 500
    res = await freeze_balance(session, "u_fr1", 500, reason="测试冻结")
    assert res.version == 2

    # 消费 600（500冻结+100可用，应该失败）
    with pytest.raises(InsufficientBalanceError):
        await debit_balance(session, "u_fr1", 600, tenant_id="default")


@pytest.mark.asyncio
async def test_unfreeze_balance(session: AsyncSession):
    """解冻后可消费。"""
    await get_or_create_account(session, "u_fr2", tenant_id="default")
    await credit_balance(session, "u_fr2", 1000, tenant_id="default")
    await freeze_balance(session, "u_fr2", 500)
    await session.commit()

    await unfreeze_balance(session, "u_fr2", 300, reason="测试解冻")
    await session.commit()

    # 现在可消费 700（1000-300冻结）
    await debit_balance(session, "u_fr2", 700, tenant_id="default")


@pytest.mark.asyncio
async def test_three_balances(session: AsyncSession):
    """查询三钱包余额。"""
    await get_or_create_account(session, "u3b", tenant_id="default")
    await credit_balance(session, "u3b", 1000, target="recharge", tenant_id="default")
    await credit_balance(session, "u3b", 500, target="income", tenant_id="default")
    await credit_balance(session, "u3b", 200, target="skin", tenant_id="default")
    await freeze_balance(session, "u3b", 300)
    await session.commit()

    bal = await get_three_balances(session, "u3b")
    assert bal.recharge_balance_cents == 1000
    assert bal.income_balance_cents == 500
    assert bal.skin_balance_cents == 200
    assert bal.frozen_cents == 300
    assert bal.available_recharge == 700  # 1000 - 300


@pytest.mark.asyncio
async def test_audit_log(session: AsyncSession):
    """写审计日志。"""
    await log_audit(
        session,
        tenant_id="default",
        user_id="u_audit",
        operator="admin",
        action="manual_credit",
        amount_cents=1000,
        balance_before=0,
        balance_after=1000,
        reason="测试调账",
    )
    await session.commit()

    from sqlalchemy import select
    result = await session.execute(select(AuditLog))
    logs = result.scalars().all()
    assert len(logs) >= 1
    assert logs[-1].action == "manual_credit"
