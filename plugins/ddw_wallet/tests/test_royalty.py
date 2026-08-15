"""课件分成测试 — 80%/50% 学科规则。"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wallet.services.account import (
    get_balance,
    get_or_create_account,
)
from plugins.ddw_wallet.services.royalty import (
    settle_royalty,
)


@pytest.mark.asyncio
async def test_royalty_default_80(session: AsyncSession):
    """数理化学习 1000 分 → 作者 +800。"""
    await get_or_create_account(session, "author_01", tenant_id="default")
    await session.commit()

    res = await settle_royalty(
        session, "author_01", "cw_001",
        "trigger_001", 1000, "physics",
    )
    await session.commit()

    assert res.income_cents == 800
    assert res.royalty_no.startswith("R")

    bal = await get_balance(session, "author_01")
    assert bal.balance_cents == 800


@pytest.mark.asyncio
async def test_royalty_english_50(session: AsyncSession):
    """英语学习 1000 分 → 作者 +500。"""
    await get_or_create_account(session, "author_02", tenant_id="default")
    await session.commit()

    res = await settle_royalty(
        session, "author_02", "cw_002",
        "trigger_002", 1000, "english",
    )
    await session.commit()

    assert res.income_cents == 500

    bal = await get_balance(session, "author_02")
    assert bal.balance_cents == 500


@pytest.mark.asyncio
async def test_royalty_idempotent(session: AsyncSession):
    """同 trigger_txn_id → 只分一次。"""
    await get_or_create_account(session, "author_03", tenant_id="default")
    await session.commit()

    r1 = await settle_royalty(
        session, "author_03", "cw_003",
        "trigger_idem_001", 1000, "math",
    )
    await session.commit()

    r2 = await settle_royalty(
        session, "author_03", "cw_003",
        "trigger_idem_001", 1000, "math",
    )
    await session.commit()

    assert r1.royalty_no == r2.royalty_no
    assert r1.income_cents == r2.income_cents == 800

    bal = await get_balance(session, "author_03")
    assert bal.balance_cents == 800  # 只加一次


@pytest.mark.asyncio
async def test_royalty_auto_create_author(
    session: AsyncSession,
):
    """作者无账户 → 自动创建。"""
    res = await settle_royalty(
        session, "new_author", "cw_004",
        "trigger_004", 1000, "chemistry",
    )
    await session.commit()

    assert res.income_cents == 800

    bal = await get_balance(session, "new_author")
    assert bal.balance_cents == 800


@pytest.mark.asyncio
async def test_royalty_subject_variations(
    session: AsyncSession,
):
    """不同学科分成比例。"""
    cases = [
        ("physics", 80),
        ("chemistry", 80),
        ("math", 80),
        ("english", 50),
        (None, 80),  # 默认
    ]
    for i, (subj, expected_rate) in enumerate(cases):
        uid = f"author_subj_{i}"
        await get_or_create_account(session, uid)
        await session.commit()

        res = await settle_royalty(
            session, uid, f"cw_s_{i}",
            f"trigger_s_{i}", 1000, subj,
        )
        expected_income = 1000 * expected_rate // 100
        assert res.income_cents == expected_income, (
            f"subject={subj}: expected {expected_income}, "
            f"got {res.income_cents}"
        )
