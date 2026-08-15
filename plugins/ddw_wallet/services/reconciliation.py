"""对账引擎（G6）— 手动触发对账，比较微信账单与本地记录。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, date
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wallet.models import RechargeOrder

logger = logging.getLogger(__name__)


@dataclass
class ReconciliationDiff:
    """对账差异。"""
    order_no: str
    local_amount: Optional[int]
    bill_amount: Optional[int]
    status: str  # matched/mismatched/local_only/bill_only


@dataclass
class ReconciliationReport:
    """对账报告。"""
    date: str
    local_total: int
    bill_total: int
    diff_total: int
    matched_count: int
    mismatched_count: int
    local_only_count: int
    bill_only_count: int
    diffs: List[ReconciliationDiff]


async def reconcile(
    session: AsyncSession,
    target_date: date,
    bill_records: Optional[List[dict]] = None,
) -> ReconciliationReport:
    """对账：比较本地充值单与微信账单。

    Args:
        target_date: 对账日期
        bill_records: 微信账单记录列表（手工传入，未来接真实 API）
            [{"out_trade_no": "...", "amount": 1000, "transaction_id": "..."}]
    """
    # 获取本地当日已支付订单
    stmt = (
        select(RechargeOrder)
        .where(
            RechargeOrder.status == "paid",
            RechargeOrder.paid_at >= datetime.combine(target_date, datetime.min.time()),
            RechargeOrder.paid_at < datetime.combine(target_date, datetime.max.time()),
        )
    )
    result = await session.execute(stmt)
    local_orders = result.scalars().all()
    local_map = {o.order_no: o.amount_cents for o in local_orders}

    bill_map = {}
    if bill_records:
        bill_map = {r["out_trade_no"]: r["amount"] for r in bill_records}

    diffs = []
    matched = mismatched = local_only = bill_only = 0
    local_total = bill_total = 0

    all_orders = set(local_map.keys()) | set(bill_map.keys())
    for order_no in sorted(all_orders):
        local_amt = local_map.get(order_no)
        bill_amt = bill_map.get(order_no)
        local_total += local_amt or 0
        bill_total += bill_amt or 0

        if local_amt is not None and bill_amt is not None:
            if local_amt == bill_amt:
                matched += 1
                status = "matched"
            else:
                mismatched += 1
                status = "mismatched"
        elif local_amt is not None:
            local_only += 1
            status = "local_only"
        else:
            bill_only += 1
            status = "bill_only"

        diffs.append(ReconciliationDiff(
            order_no=order_no,
            local_amount=local_amt,
            bill_amount=bill_amt,
            status=status,
        ))

    return ReconciliationReport(
        date=target_date.isoformat(),
        local_total=local_total,
        bill_total=bill_total,
        diff_total=abs(local_total - bill_total),
        matched_count=matched,
        mismatched_count=mismatched,
        local_only_count=local_only,
        bill_only_count=bill_only,
        diffs=diffs,
    )
