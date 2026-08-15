"""G4 混合扣费 + G5 平台抽佣测试。"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wallet.services.account import (
    InsufficientBalanceError,
    credit_balance,
    get_or_create_account,
)
from plugins.ddw_wallet.services.charge import (
    charge_with_fallback,
    settle_platform_fee,
)


@pytest.mark.asyncio
async def test_charge_with_fallback_recharge_sufficient(session: AsyncSession):
    """recharge 钱包充足 → 直接扣 recharge。"""
    await get_or_create_account(session, "u_f1", tenant_id="default")
    await credit_balance(session, "u_f1", 1000, target="recharge", tenant_id="default")
    await session.commit()

    res = await charge_with_fallback(
        session, "u_f1", 500, "ref_f1", "study_time",
    )
    assert res.amount_cents == 500
    assert res.balance_after == 500


@pytest.mark.asyncio
async def test_charge_with_fallback_income_sufficient(session: AsyncSession):
    """recharge 不足 → 扣 income。"""
    await get_or_create_account(session, "u_f2", tenant_id="default")
    await credit_balance(session, "u_f2", 200, target="recharge", tenant_id="default")
    await credit_balance(session, "u_f2", 500, target="income", tenant_id="default")
    await session.commit()

    res = await charge_with_fallback(
        session, "u_f2", 500, "ref_f2", "study_time",
    )
    assert res.amount_cents == 500


@pytest.mark.asyncio
async def test_charge_with_fallback_all_insufficient(session: AsyncSession):
    """三钱包全不足 → 402。"""
    await get_or_create_account(session, "u_f3", tenant_id="default")
    await credit_balance(session, "u_f3", 100, target="recharge", tenant_id="default")
    await session.commit()

    with pytest.raises(InsufficientBalanceError):
        await charge_with_fallback(
            session, "u_f3", 500, "ref_f3", "study_time",
        )


@pytest.mark.asyncio
async def test_charge_with_fallback_idempotent(session: AsyncSession):
    """幂等：同一 ref_id 只扣一次。"""
    await get_or_create_account(session, "u_f4", tenant_id="default")
    await credit_balance(session, "u_f4", 1000, target="recharge", tenant_id="default")
    await session.commit()

    res1 = await charge_with_fallback(
        session, "u_f4", 300, "ref_f4", "study_time",
    )
    res2 = await charge_with_fallback(
        session, "u_f4", 300, "ref_f4", "study_time",
    )
    assert res1.txn_no == res2.txn_no  # 幂等返回同一流水


@pytest.mark.asyncio
async def test_settle_platform_fee_default_5pct(session: AsyncSession):
    """平台抽佣 5%（默认）。"""
    fee = await settle_platform_fee(session, "TXN_001", 1000)
    assert fee == 50  # 1000 * 5% = 50

    # 幂等
    fee2 = await settle_platform_fee(session, "TXN_001", 1000)
    assert fee2 == 50  # 同 txn 只抽一次


@pytest.mark.asyncio
async def test_settle_platform_fee_custom(session: AsyncSession):
    """自定义抽佣比例（通过环境变量）。"""
    import os
    old_val = os.environ.get("DDW_WALLET_PLATFORM_FEE_PERCENT")
    os.environ["DDW_WALLET_PLATFORM_FEE_PERCENT"] = "10"
    try:
        import importlib
        from plugins.ddw_wallet.services import charge
        importlib.reload(charge)
        fee = await settle_platform_fee(session, "TXN_002", 2000)
        assert fee == 200  # 2000 * 10% = 200
    finally:
        if old_val:
            os.environ["DDW_WALLET_PLATFORM_FEE_PERCENT"] = old_val
        else:
            del os.environ["DDW_WALLET_PLATFORM_FEE_PERCENT"]
        importlib.reload(charge)
