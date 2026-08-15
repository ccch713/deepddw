from __future__ import annotations

"""DDW 财务看板插件业务逻辑层。

本插件为只读聚合查询层：
- 不创建新表
- 不调用 LLM
- 通过 SQLAlchemy 跨插件 query P1-1 合同 / P1-3 应收 / P1-4 实收 ORM 模型
- 金额字段全部用 ``func.coalesce(func.sum(...), 0)`` 由 SQL 端聚合，
  避免 Python 端 float 精度漂移
- 跨插件 JOIN 用 ``select(...).outerjoin(...)`` 显式表达
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Dict, List, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_company_profile.models import Company
from plugins.ddw_contract_core.models import Contract
from plugins.ddw_offline_pos.models import Payment
from plugins.ddw_receivable.models import Receivable

from .schemas import (
    OutstandingByCompanyItem,
    OverdueItem,
    OverdueResp,
    OverviewResp,
    StatsResp,
    TrendItem,
    TrendResp,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 内部常量
# ---------------------------------------------------------------------------

ZERO = Decimal("0")

# 合同"已签"统计覆盖的状态（与 manifest.yaml 配置一致）
SIGNED_STATUSES: Tuple[str, ...] = ("signed", "active", "completed")


# ---------------------------------------------------------------------------
# DashboardService
# ---------------------------------------------------------------------------


class DashboardService:
    """财务看板聚合查询服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # 1. Overview（财务总览）
    # ------------------------------------------------------------------ #

    async def overview(self, tenant_id: int = 1) -> OverviewResp:
        """总览：合同 / 应收 / 实收 / 逾期 四维度。

        所有金额字段走 SQL 端 ``func.coalesce(func.sum(...), 0)`` 聚合。
        """
        # ---- 1) 合同总览 ----
        contracts_total = (
            await self.db.execute(
                select(func.count(Contract.id)).where(Contract.tenant_id == tenant_id)
            )
        ).scalar_one()

        contracts_signed = (
            await self.db.execute(
                select(func.count(Contract.id)).where(
                    Contract.tenant_id == tenant_id,
                    Contract.status.in_(SIGNED_STATUSES),
                )
            )
        ).scalar_one()

        contracts_total_amount = (
            await self.db.execute(
                select(func.coalesce(func.sum(Contract.total_amount), 0)).where(
                    Contract.tenant_id == tenant_id
                )
            )
        ).scalar_one()

        contracts_signed_amount = (
            await self.db.execute(
                select(func.coalesce(func.sum(Contract.total_amount), 0)).where(
                    Contract.tenant_id == tenant_id,
                    Contract.status.in_(SIGNED_STATUSES),
                )
            )
        ).scalar_one()

        # ---- 2) 应收总览 ----
        receivables_total = (
            await self.db.execute(
                select(func.count(Receivable.id)).where(
                    Receivable.tenant_id == tenant_id
                )
            )
        ).scalar_one()

        recv_amt = (
            await self.db.execute(
                select(
                    func.coalesce(func.sum(Receivable.amount), 0).label("amt"),
                    func.coalesce(func.sum(Receivable.paid_amount), 0).label("paid"),
                ).where(Receivable.tenant_id == tenant_id)
            )
        ).one()
        receivables_total_amount = Decimal(recv_amt.amt or 0)
        receivables_paid_amount = Decimal(recv_amt.paid or 0)
        receivables_outstanding_amount = receivables_total_amount - receivables_paid_amount

        # ---- 3) 实收总览 ----
        payments_total = (
            await self.db.execute(
                select(func.count(Payment.id)).where(Payment.tenant_id == tenant_id)
            )
        ).scalar_one()

        pay_amt = (
            await self.db.execute(
                select(
                    func.coalesce(func.sum(Payment.amount), 0).label("amt"),
                    func.coalesce(func.sum(Payment.matched_amount), 0).label("matched"),
                ).where(Payment.tenant_id == tenant_id)
            )
        ).one()
        payments_total_amount = Decimal(pay_amt.amt or 0)
        payments_matched_amount = Decimal(pay_amt.matched or 0)
        payments_unmatched_amount = payments_total_amount - payments_matched_amount

        # ---- 4) 逾期（amount - paid_amount） ----
        overdue_stats = (
            await self.db.execute(
                select(
                    func.count(Receivable.id).label("cnt"),
                    func.coalesce(
                        func.sum(Receivable.amount - Receivable.paid_amount), 0
                    ).label("amt"),
                ).where(
                    Receivable.tenant_id == tenant_id,
                    Receivable.status == "overdue",
                )
            )
        ).one()
        overdue_count = int(overdue_stats.cnt or 0)
        overdue_amount = Decimal(overdue_stats.amt or 0)

        return OverviewResp(
            tenant_id=tenant_id,
            contracts_total=contracts_total,
            contracts_signed=contracts_signed,
            contracts_total_amount=Decimal(contracts_total_amount or 0),
            contracts_signed_amount=Decimal(contracts_signed_amount or 0),
            receivables_total=receivables_total,
            receivables_total_amount=receivables_total_amount,
            receivables_paid_amount=receivables_paid_amount,
            receivables_outstanding_amount=receivables_outstanding_amount,
            payments_total=payments_total,
            payments_total_amount=payments_total_amount,
            payments_matched_amount=payments_matched_amount,
            payments_unmatched_amount=payments_unmatched_amount,
            overdue_count=overdue_count,
            overdue_amount=overdue_amount,
        )

    # ------------------------------------------------------------------ #
    # 2. Overdue（逾期列表）
    # ------------------------------------------------------------------ #

    async def overdue(self, tenant_id: int = 1, limit: int = 100) -> OverdueResp:
        """逾期列表：按 (amount - paid_amount) 降序的 top N。

        LEFT JOIN crm_companies 拿企业名（企业被归档时为 NULL）。
        """
        # ---- 总额：所有 overdue 应收的 (amount - paid_amount) 之和 ----
        # 注意：直接 sum 表达式，避免 Python 端精度漂移
        total_stmt = select(
            func.coalesce(
                func.sum(Receivable.amount - Receivable.paid_amount), 0
            )
        ).where(
            Receivable.tenant_id == tenant_id,
            Receivable.status == "overdue",
        )
        total_overdue_amount = (await self.db.execute(total_stmt)).scalar_one()

        # ---- 列表：LEFT JOIN + 排序 + limit ----
        outstanding_expr = (Receivable.amount - Receivable.paid_amount).label(
            "outstanding"
        )
        stmt = (
            select(
                Receivable.id,
                Receivable.tenant_id,
                Receivable.company_id,
                Company.name.label("company_name"),
                Receivable.contract_id,
                Receivable.node_name,
                Receivable.amount,
                Receivable.paid_amount,
                outstanding_expr,
                Receivable.due_date,
                Receivable.status,
            )
            .outerjoin(Company, Company.id == Receivable.company_id)
            .where(
                Receivable.tenant_id == tenant_id,
                Receivable.status == "overdue",
            )
            .order_by(outstanding_expr.desc(), Receivable.id.desc())
            .limit(limit)
        )
        rows = (await self.db.execute(stmt)).all()

        items: List[OverdueItem] = []
        for (
            rid,
            rtid,
            company_id,
            company_name,
            contract_id,
            node_name,
            amount,
            paid_amount,
            outstanding,
            due_date,
            status,
        ) in rows:
            items.append(
                OverdueItem(
                    id=rid,
                    tenant_id=rtid,
                    company_id=company_id,
                    company_name=company_name,
                    contract_id=contract_id,
                    node_name=node_name,
                    amount=Decimal(amount or 0),
                    paid_amount=Decimal(paid_amount or 0),
                    outstanding_amount=Decimal(outstanding or 0),
                    due_date=due_date,
                    status=status,
                )
            )

        return OverdueResp(
            tenant_id=tenant_id,
            total=len(items),
            total_overdue_amount=Decimal(total_overdue_amount or 0),
            items=items,
        )

    # ------------------------------------------------------------------ #
    # 3. Trend（最近 N 月应收 + 实收）
    # ------------------------------------------------------------------ #

    @staticmethod
    def _month_window(anchor: date, months: int) -> List[str]:
        """生成从 ``anchor`` 倒推 ``months`` 个月的连续月份列表（含 anchor 当月）。

        例：anchor=2026-05, months=12 →
        ['2025-06', '2025-07', ..., '2026-05']（共 12 项）
        """
        keys: List[str] = []
        y, m = anchor.year, anchor.month
        for _ in range(months):
            keys.append(f"{y:04d}-{m:02d}")
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        # 上面循环倒序，flip 成升序
        return list(reversed(keys))

    async def trend(self, tenant_id: int = 1, months: int = 12) -> TrendResp:
        """趋势：最近 ``months`` 个月，按 due_date 聚合应收 + 按 payment_date 聚合实收。

        - receivable_amount：当月所有应收的 amount 之和（按 due_date）
        - payment_amount：当月所有实收的 amount 之和（按 payment_date）
        - net = receivable - payment

        缺失月份补 0，保证返回的 month 序列连续无空洞。
        """
        today = date.today()
        month_keys = self._month_window(today, months)
        oldest_year_month = month_keys[0]
        fy, fm = int(oldest_year_month[:4]), int(oldest_year_month[5:7])
        window_start = date(fy, fm, 1)
        next_month_start = _add_months(date(today.year, today.month, 1), 1)

        # ---- 应收：按 due_date 聚合 ----
        # SQLite 用 strftime；PG 也支持 strftime
        recv_month_expr = func.strftime("%Y-%m", Receivable.due_date).label("m")
        stmt_recv = (
            select(
                recv_month_expr,
                func.coalesce(func.sum(Receivable.amount), 0).label("amt"),
            )
            .where(
                Receivable.tenant_id == tenant_id,
                Receivable.due_date >= window_start,
                Receivable.due_date < next_month_start,
            )
            .group_by("m")
        )
        recv_rows = (await self.db.execute(stmt_recv)).all()
        recv_by_month: Dict[str, Decimal] = {m: Decimal(amt) for m, amt in recv_rows}

        # ---- 实收：按 payment_date 聚合 ----
        pay_month_expr = func.strftime("%Y-%m", Payment.payment_date).label("m")
        stmt_pay = (
            select(
                pay_month_expr,
                func.coalesce(func.sum(Payment.amount), 0).label("amt"),
            )
            .where(
                Payment.tenant_id == tenant_id,
                Payment.payment_date >= window_start,
                Payment.payment_date < next_month_start,
            )
            .group_by("m")
        )
        pay_rows = (await self.db.execute(stmt_pay)).all()
        pay_by_month: Dict[str, Decimal] = {m: Decimal(amt) for m, amt in pay_rows}

        # ---- 拼装（补 0） ----
        items: List[TrendItem] = []
        for mk in month_keys:
            recv_amt = recv_by_month.get(mk, ZERO)
            pay_amt = pay_by_month.get(mk, ZERO)
            items.append(
                TrendItem(
                    month=mk,
                    receivable_amount=recv_amt,
                    payment_amount=pay_amt,
                    net=recv_amt - pay_amt,
                )
            )

        return TrendResp(tenant_id=tenant_id, months=months, items=items)

    # ------------------------------------------------------------------ #
    # 4. Stats（按状态分布 + 按企业未收金额）
    # ------------------------------------------------------------------ #

    async def stats(self, tenant_id: int = 1) -> StatsResp:
        """财务统计：4 个维度的分布 + 按企业未收金额 top 50。"""
        # ---- 合同：按 status 分组的 count + amount ----
        contract_rows = (
            await self.db.execute(
                select(
                    Contract.status,
                    func.count(Contract.id).label("cnt"),
                    func.coalesce(func.sum(Contract.total_amount), 0).label("amt"),
                )
                .where(Contract.tenant_id == tenant_id)
                .group_by(Contract.status)
            )
        ).all()
        contracts_by_status: Dict[str, int] = {s: int(c) for s, c, _ in contract_rows}
        contracts_amount_by_status: Dict[str, Decimal] = {
            s: Decimal(a or 0) for s, _, a in contract_rows
        }

        # ---- 应收：按 status 分组的 count + amount + outstanding ----
        recv_rows = (
            await self.db.execute(
                select(
                    Receivable.status,
                    func.count(Receivable.id).label("cnt"),
                    func.coalesce(func.sum(Receivable.amount), 0).label("amt"),
                    func.coalesce(
                        func.sum(Receivable.amount - Receivable.paid_amount), 0
                    ).label("outstanding"),
                )
                .where(Receivable.tenant_id == tenant_id)
                .group_by(Receivable.status)
            )
        ).all()
        receivables_by_status: Dict[str, int] = {s: int(c) for s, c, _, _ in recv_rows}
        receivables_amount_by_status: Dict[str, Decimal] = {
            s: Decimal(a or 0) for s, _, a, _ in recv_rows
        }
        receivables_outstanding_by_status: Dict[str, Decimal] = {
            s: Decimal(o or 0) for s, _, _, o in recv_rows
        }

        # ---- 实收：按 status 分组的 count + amount ----
        pay_rows = (
            await self.db.execute(
                select(
                    Payment.status,
                    func.count(Payment.id).label("cnt"),
                    func.coalesce(func.sum(Payment.amount), 0).label("amt"),
                )
                .where(Payment.tenant_id == tenant_id)
                .group_by(Payment.status)
            )
        ).all()
        payments_by_status: Dict[str, int] = {s: int(c) for s, c, _ in pay_rows}
        payments_amount_by_status: Dict[str, Decimal] = {
            s: Decimal(a or 0) for s, _, a in pay_rows
        }

        # ---- 按企业未收金额：只统计未付清（status in pending/partial/overdue） ----
        outstanding_expr = func.coalesce(
            func.sum(Receivable.amount - Receivable.paid_amount), 0
        ).label("outstanding")
        company_rows = (
            await self.db.execute(
                select(
                    Receivable.company_id,
                    Company.name.label("company_name"),
                    func.count(Receivable.id).label("cnt"),
                    outstanding_expr,
                )
                .outerjoin(Company, Company.id == Receivable.company_id)
                .where(
                    Receivable.tenant_id == tenant_id,
                    Receivable.status.in_(("pending", "partial", "overdue")),
                )
                .group_by(Receivable.company_id, Company.name)
                .order_by(outstanding_expr.desc())
                .limit(50)
            )
        ).all()
        receivables_outstanding_by_company: List[OutstandingByCompanyItem] = []
        for company_id, company_name, cnt, outstanding in company_rows:
            receivables_outstanding_by_company.append(
                OutstandingByCompanyItem(
                    company_id=company_id,
                    company_name=company_name,
                    outstanding_amount=Decimal(outstanding or 0),
                    receivable_count=int(cnt or 0),
                )
            )

        return StatsResp(
            tenant_id=tenant_id,
            contracts_by_status=contracts_by_status,
            contracts_amount_by_status=contracts_amount_by_status,
            receivables_by_status=receivables_by_status,
            receivables_amount_by_status=receivables_amount_by_status,
            receivables_outstanding_by_status=receivables_outstanding_by_status,
            payments_by_status=payments_by_status,
            payments_amount_by_status=payments_amount_by_status,
            receivables_outstanding_by_company=receivables_outstanding_by_company,
        )


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _add_months(d: date, n: int) -> date:
    """日期 +n 月（按月末截断），用于生成 SQL 区间上界。

    n=1：返回下个月 1 号；n=-1：返回上个月 1 号。
    """
    y = d.year
    m = d.month + n
    while m > 12:
        m -= 12
        y += 1
    while m < 1:
        m += 12
        y -= 1
    return date(y, m, 1)


__all__ = ["DashboardService", "SIGNED_STATUSES"]
