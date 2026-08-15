"""按量扣费测试。"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wallet.services.account import (
    InsufficientBalanceError,
    credit_balance,
    get_or_create_account,
)
from plugins.ddw_wallet.services.charge import charge


@pytest.mark.asyncio
async def test_charge_success(session: AsyncSession):
    """扣费 100 分 → balance_after 正确，流水生成。"""
    await get_or_create_account(session, "u_ch1", tenant_id="default")
    await session.commit()

    await credit_balance(session, "u_ch1", 500, tenant_id="default")

    res = await charge(
        session, "u_ch1", "study_time", None,
        "ref_001", "session", 100,
    )
    await session.commit()

    assert res.amount_cents == 100
    assert res.balance_after == 400
    assert res.txn_no.startswith("C")


@pytest.mark.asyncio
async def test_charge_insufficient(session: AsyncSession):
    """余额不足 → InsufficientBalanceError。"""
    await get_or_create_account(session, "u_ch2", tenant_id="default")
    await session.commit()

    await credit_balance(session, "u_ch2", 50, tenant_id="default")

    with pytest.raises(InsufficientBalanceError):
        await charge(
            session, "u_ch2", "study_time", None,
            "ref_002", "session", 100,
        )


@pytest.mark.asyncio
async def test_charge_idempotent(session: AsyncSession):
    """同 ref_id 二次扣费 → 返回首次流水，不再扣。"""
    await get_or_create_account(session, "u_ch3", tenant_id="default")
    await session.commit()

    await credit_balance(session, "u_ch3", 500, tenant_id="default")

    res1 = await charge(
        session, "u_ch3", "study_time", None,
        "ref_idem_001", "session", 100,
    )
    await session.commit()

    res2 = await charge(
        session, "u_ch3", "study_time", None,
        "ref_idem_001", "session", 100,
    )
    await session.commit()

    assert res1.txn_no == res2.txn_no
    assert res1.balance_after == res2.balance_after
    # 余额只扣了一次
    assert res1.balance_after == 400


@pytest.mark.asyncio
async def test_charge_different_types(
    session: AsyncSession,
):
    """不同 charge_type 可用。"""
    await get_or_create_account(session, "u_ch4", tenant_id="default")
    await session.commit()

    await credit_balance(session, "u_ch4", 1000, tenant_id="default")

    await charge(
        session, "u_ch4", "study_time", "physics",
        "ref_t1", "session", 100,
    )
    await charge(
        session, "u_ch4", "voice", None,
        "ref_t2", "session", 200,
    )
    r3 = await charge(
        session, "u_ch4", "courseware", "english",
        "ref_t3", "generation", 300,
    )
    await session.commit()

    assert r3.balance_after == 400
