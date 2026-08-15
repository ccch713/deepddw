"""G6 对账引擎测试。"""
import pytest
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wallet.services.reconciliation import reconcile


@pytest.mark.asyncio
async def test_reconcile_matched(session: AsyncSession):
    """对账：金额匹配。"""
    report = await reconcile(
        session,
        date(2026, 8, 12),
        bill_records=[
            {"out_trade_no": "ORD1", "amount": 1000, "transaction_id": "TX1"},
        ],
    )
    assert report.matched_count == 0  # 本地无 ORD1，属于 bill_only
    assert report.bill_only_count == 1


@pytest.mark.asyncio
async def test_reconcile_mismatched(session: AsyncSession):
    """对账：金额不符。"""
    report = await reconcile(
        session,
        date(2026, 8, 12),
        bill_records=[
            {"out_trade_no": "ORD2", "amount": 999, "transaction_id": "TX2"},
        ],
    )
    assert report.bill_only_count == 1  # 本地无 ORD2


@pytest.mark.asyncio
async def test_reconcile_empty(session: AsyncSession):
    """对账：空账单。"""
    report = await reconcile(session, date(2026, 8, 12))
    assert report.matched_count == 0
    assert report.mismatched_count == 0
    assert report.local_total == 0
