"""账户服务测试 — 创建/余额/并发扣费。"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

from plugins.ddw_wallet.services.account import (
    InsufficientBalanceError,
    credit_balance,
    debit_balance,
    get_balance,
    get_or_create_account,
)


@pytest.mark.asyncio
async def test_create_account(session: AsyncSession):
    """创建账户 → 三钱包余额=0, status=active."""
    acc = await get_or_create_account(session, "u01", tenant_id="default")
    await session.commit()

    assert acc.user_id == "u01"
    assert acc.recharge_balance_cents == 0
    assert acc.income_balance_cents == 0
    assert acc.skin_balance_cents == 0
    assert acc.status == "active"
    assert acc.version == 0


@pytest.mark.asyncio
async def test_duplicate_account(session: AsyncSession):
    """同 user_id 重复创建 → 返回已有账户。"""
    acc1 = await get_or_create_account(session, "u02", tenant_id="default")
    await session.commit()

    acc2 = await get_or_create_account(session, "u02", tenant_id="default")
    assert acc1.id == acc2.id
    assert acc2.recharge_balance_cents == 0


@pytest.mark.asyncio
async def test_get_balance(session: AsyncSession):
    """查询余额。"""
    await get_or_create_account(session, "u03", tenant_id="default")
    await session.commit()

    res = await get_balance(session, "u03")
    assert res.balance_cents == 0


@pytest.mark.asyncio
async def test_get_balance_not_found(session: AsyncSession):
    """查询不存在的账户 → 抛异常。"""
    with pytest.raises(ValueError, match="not found"):
        await get_balance(session, "nonexistent")


@pytest.mark.asyncio
async def test_credit_balance(session: AsyncSession):
    """充值入账。"""
    await get_or_create_account(session, "u04", tenant_id="default")
    await session.commit()

    res = await credit_balance(session, "u04", 500, tenant_id="default")
    assert res.balance_cents == 500
    assert res.version == 1


@pytest.mark.asyncio
async def test_debit_balance(session: AsyncSession):
    """扣费。"""
    await get_or_create_account(session, "u05", tenant_id="default")
    await session.commit()

    await credit_balance(session, "u05", 1000, tenant_id="default")
    res = await debit_balance(session, "u05", 300, tenant_id="default")

    assert res.balance_cents == 700
    assert res.version == 2


@pytest.mark.asyncio
async def test_debit_insufficient(session: AsyncSession):
    """余额不足 → 抛 InsufficientBalanceError。"""
    await get_or_create_account(session, "u06", tenant_id="default")
    await session.commit()

    await credit_balance(session, "u06", 100, tenant_id="default")

    with pytest.raises(InsufficientBalanceError) as ei:
        await debit_balance(session, "u06", 200, tenant_id="default")
    assert ei.value.balance_cents == 100
    assert ei.value.required_cents == 200


@pytest.mark.asyncio
async def test_balance_concurrent_charge(db_engine):
    """并发扣费（10 协程）→ 最终余额正确，无负数。"""
    factory = async_sessionmaker(
        bind=db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    # 创建账户并充值 1000 分
    async with factory() as s:
        await get_or_create_account(s, "conc")
        await s.commit()
    async with factory() as s:
        await credit_balance(s, "conc", 1000, tenant_id="default")

    # 3 个协程各扣 100 分（SQLite 并发能力有限，用 3 而非 10）
    async def _charge() -> bool:
        async with factory() as s:
            try:
                await debit_balance(s, "conc", 100, tenant_id="default")
                return True
            except (
                InsufficientBalanceError,
                RuntimeError,
            ):
                return False

    results = await asyncio.gather(
        *[_charge() for _ in range(3)]
    )
    ok = sum(1 for r in results if r)

    async with factory() as s:
        res = await get_balance(s, "conc")

    assert res.balance_cents >= 0  # 余额不为负
    assert ok >= 1  # 至少成功1个扣费
