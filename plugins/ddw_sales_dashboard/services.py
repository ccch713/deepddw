from __future__ import annotations

"""DDW 销售看板插件业务逻辑层。

本插件为只读聚合查询层：
- 不创建新表
- 不调用 LLM
- 通过 SQLAlchemy 跨插件 query P0-1~P0-4 的 ORM 模型
- 金额字段全部用 ``func.coalesce(func.sum(...), 0)`` 由 SQL 端聚合，
  避免 Python 端 float 精度漂移
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Dict, List, Tuple

from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_company_profile.models import Company
from plugins.ddw_contact_hub.models import Contact
from plugins.ddw_opportunity.models import Opportunity
from plugins.ddw_opportunity.services import STAGE_DISPLAY_ORDER, STAGE_LABELS
from plugins.ddw_quotation.models import Quotation

from .schemas import (
    FunnelItem,
    FunnelResp,
    OverviewResp,
    RankingItem,
    RankingResp,
    RecentOpportunityItem,
    RecentOpportunityResp,
    StageDistributionItem,
    StageDistributionResp,
    TrendItem,
    TrendResp,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 内部常量
# ---------------------------------------------------------------------------

ZERO = Decimal("0")


# ---------------------------------------------------------------------------
# DashboardService
# ---------------------------------------------------------------------------


class DashboardService:
    """销售看板聚合查询服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # 1. Overview
    # ------------------------------------------------------------------ #

    async def overview(self, tenant_id: int = 1) -> OverviewResp:
        """总览：企业 / 联系人 / 商机 / 报价 / 金额 / 成交客户数。

        所有金额字段走 SQL 端 ``func.coalesce(func.sum(...), 0)`` 聚合。
        """
        # 1) COUNT 类（4 个）
        companies = (
            await self.db.execute(
                select(func.count(Company.id)).where(Company.tenant_id == tenant_id)
            )
        ).scalar_one()
        contacts = (
            await self.db.execute(
                select(func.count(Contact.id)).where(Contact.tenant_id == tenant_id)
            )
        ).scalar_one()
        opportunities = (
            await self.db.execute(
                select(func.count(Opportunity.id)).where(Opportunity.tenant_id == tenant_id)
            )
        ).scalar_one()
        quotations = (
            await self.db.execute(
                select(func.count(Quotation.id)).where(Quotation.tenant_id == tenant_id)
            )
        ).scalar_one()

        # 2) 进行中（open）商机预计金额
        estimated_amount = (
            await self.db.execute(
                select(func.coalesce(func.sum(Opportunity.estimated_amount), 0)).where(
                    Opportunity.tenant_id == tenant_id,
                    Opportunity.status == "open",
                )
            )
        ).scalar_one()

        # 3) 成交金额（status=won 的 estimated_amount 之和）
        won_amount = (
            await self.db.execute(
                select(func.coalesce(func.sum(Opportunity.estimated_amount), 0)).where(
                    Opportunity.tenant_id == tenant_id,
                    Opportunity.status == "won",
                )
            )
        ).scalar_one()

        # 4) 成交客户数：去重 company_id
        won_customers = (
            await self.db.execute(
                select(func.count(distinct(Opportunity.company_id))).where(
                    Opportunity.tenant_id == tenant_id,
                    Opportunity.status == "won",
                    Opportunity.company_id.isnot(None),
                )
            )
        ).scalar_one()

        # 5) 业务语义补充：open / won / lost 商机数
        by_status_rows = (
            await self.db.execute(
                select(Opportunity.status, func.count(Opportunity.id))
                .where(Opportunity.tenant_id == tenant_id)
                .group_by(Opportunity.status)
            )
        ).all()
        by_status: Dict[str, int] = {s: c for s, c in by_status_rows}

        # 6) 报价单已接受数 + 已接受金额
        accepted_count = (
            await self.db.execute(
                select(func.count(Quotation.id)).where(
                    Quotation.tenant_id == tenant_id,
                    Quotation.status == "accepted",
                )
            )
        ).scalar_one()
        accepted_amount = (
            await self.db.execute(
                select(func.coalesce(func.sum(Quotation.final_amount), 0)).where(
                    Quotation.tenant_id == tenant_id,
                    Quotation.status == "accepted",
                )
            )
        ).scalar_one()

        return OverviewResp(
            tenant_id=tenant_id,
            companies=companies,
            contacts=contacts,
            opportunities=opportunities,
            quotations=quotations,
            estimated_amount=Decimal(estimated_amount or 0),
            won_amount=Decimal(won_amount or 0),
            won_customers=won_customers,
            open_opportunities=by_status.get("open", 0),
            won_opportunities=by_status.get("won", 0),
            lost_opportunities=by_status.get("lost", 0),
            accepted_quotations=accepted_count,
            accepted_amount=Decimal(accepted_amount or 0),
        )

    # ------------------------------------------------------------------ #
    # 2. Funnel（按 stage 全量，含 won / lost）
    # ------------------------------------------------------------------ #

    async def funnel(self, tenant_id: int = 1) -> FunnelResp:
        """漏斗：按 stage 分组，含 count + total_amount（**含已成交/丢单**）。

        与 P0-3 ``OpportunityService.funnel`` 的区别：
        - P0-3 仅统计 ``status == 'open'`` 的进行中商机
        - 本接口是 dashboard 全量视角，包含 won / lost 的终止态
        """
        stmt = (
            select(
                Opportunity.stage,
                func.count(Opportunity.id).label("cnt"),
                func.coalesce(func.sum(Opportunity.estimated_amount), 0).label("amt"),
            )
            .where(Opportunity.tenant_id == tenant_id)
            .group_by(Opportunity.stage)
        )
        rows = (await self.db.execute(stmt)).all()
        by_stage: Dict[str, Tuple[int, Decimal]] = {
            stage: (cnt, Decimal(amt)) for stage, cnt, amt in rows
        }

        items: List[FunnelItem] = []
        total = 0
        total_amount = ZERO
        for stage in STAGE_DISPLAY_ORDER:
            cnt, amt = by_stage.get(stage, (0, ZERO))
            items.append(
                FunnelItem(
                    stage=stage,
                    stage_label=STAGE_LABELS.get(stage, ""),
                    count=cnt,
                    total_amount=amt,
                )
            )
            total += cnt
            total_amount += amt

        return FunnelResp(
            tenant_id=tenant_id,
            stages=items,
            total=total,
            total_amount=total_amount,
        )

    # ------------------------------------------------------------------ #
    # 3. Trend（最近 N 月）
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
        """趋势：最近 ``months`` 个月，按 created_at 聚合。

        - new_opportunities：按 created_at 所在月份
        - total_amount：按 created_at 所在月份
        - won_amount：按 won_at 所在月份（NULL won_at 不计）

        缺失月份补 0，保证返回的 month 序列连续无空洞。
        """
        # 锚点：当前日期所在月
        today = date.today()
        month_keys = self._month_window(today, months)
        oldest_year_month = month_keys[0]  # 'YYYY-MM'

        # 当月起点（含）和上界
        first_of_anchor = date(today.year, today.month, 1)
        # 计算窗口起点
        fy, fm = int(oldest_year_month[:4]), int(oldest_year_month[5:7])
        window_start = date(fy, fm, 1)

        # ---- 新增商机 / 总金额（按 created_at） ----
        # SQLite 用 strftime；PG 用 to_char。统一走 func.cast + strftime 兼容 SQLite + PG
        # （PG 也支持 strftime 来自 pg_catalog，SQLite 原生支持）
        # 月份表达式（SQLite 原生 strftime；PG 也兼容）
        created_month_expr = func.strftime("%Y-%m", Opportunity.created_at).label("m")
        next_month_start = _add_months(first_of_anchor, 1)
        stmt_new = (
            select(
                created_month_expr,
                func.count(Opportunity.id).label("cnt"),
                func.coalesce(func.sum(Opportunity.estimated_amount), 0).label("amt"),
            )
            .where(
                Opportunity.tenant_id == tenant_id,
                Opportunity.created_at >= window_start,
                Opportunity.created_at < next_month_start,
            )
            .group_by("m")
        )
        new_rows = (await self.db.execute(stmt_new)).all()
        new_by_month: Dict[str, Tuple[int, Decimal]] = {
            m: (cnt, Decimal(amt)) for m, cnt, amt in new_rows
        }

        # ---- 成交金额（按 won_at） ----
        won_month_expr = func.strftime("%Y-%m", Opportunity.won_at).label("m")
        stmt_won = (
            select(
                won_month_expr,
                func.coalesce(func.sum(Opportunity.estimated_amount), 0).label("amt"),
            )
            .where(
                Opportunity.tenant_id == tenant_id,
                Opportunity.status == "won",
                Opportunity.won_at.isnot(None),
                Opportunity.won_at >= window_start,
                Opportunity.won_at < next_month_start,
            )
            .group_by("m")
        )
        won_rows = (await self.db.execute(stmt_won)).all()
        won_by_month: Dict[str, Decimal] = {m: Decimal(amt) for m, amt in won_rows}

        # ---- 拼装（补 0） ----
        items: List[TrendItem] = []
        for mk in month_keys:
            new_cnt, new_amt = new_by_month.get(mk, (0, ZERO))
            won_amt = won_by_month.get(mk, ZERO)
            items.append(
                TrendItem(
                    month=mk,
                    new_opportunities=new_cnt,
                    total_amount=new_amt,
                    won_amount=won_amt,
                )
            )

        return TrendResp(tenant_id=tenant_id, months=months, items=items)

    # ------------------------------------------------------------------ #
    # 4. Ranking（按 owner_id 聚合）
    # ------------------------------------------------------------------ #

    async def ranking(self, tenant_id: int = 1) -> RankingResp:
        """销售排行：按 owner_id 分组聚合，按 estimated_amount 降序。

        - 排除 owner_id IS NULL 的记录（无法归因）
        - win_rate 仅基于「终止态」（won + lost），open 商机不计入分母
        """
        # 用 case when 把 won/lost 拆出来，避免多次 query
        won_amount_expr = func.coalesce(
            func.sum(
                case(
                    (Opportunity.status == "won", Opportunity.estimated_amount),
                    else_=0,
                )
            ),
            0,
        )
        won_count_expr = func.coalesce(
            func.sum(case((Opportunity.status == "won", 1), else_=0)), 0
        )
        lost_count_expr = func.coalesce(
            func.sum(case((Opportunity.status == "lost", 1), else_=0)), 0
        )
        total_amount_expr = func.coalesce(func.sum(Opportunity.estimated_amount), 0)

        stmt = (
            select(
                Opportunity.owner_id.label("owner_id"),
                func.count(Opportunity.id).label("total"),
                total_amount_expr.label("amt"),
                won_amount_expr.label("wamt"),
                won_count_expr.label("wcnt"),
                lost_count_expr.label("lcnt"),
            )
            .where(
                Opportunity.tenant_id == tenant_id,
                Opportunity.owner_id.isnot(None),
            )
            .group_by(Opportunity.owner_id)
            .order_by(total_amount_expr.desc())
        )
        rows = (await self.db.execute(stmt)).all()

        items: List[RankingItem] = []
        for owner_id, total, amt, wamt, wcnt, lcnt in rows:
            denom = (wcnt or 0) + (lcnt or 0)
            win_rate = (wcnt / denom) if denom > 0 else 0.0
            items.append(
                RankingItem(
                    owner_id=owner_id,
                    total_opportunities=total,
                    estimated_amount=Decimal(amt or 0),
                    won_amount=Decimal(wamt or 0),
                    won_count=int(wcnt or 0),
                    lost_count=int(lcnt or 0),
                    win_rate=round(float(win_rate), 4),
                )
            )

        return RankingResp(
            tenant_id=tenant_id,
            items=items,
            total_owners=len(items),
        )

    # ------------------------------------------------------------------ #
    # 5. Recent（最近 N 个商机）
    # ------------------------------------------------------------------ #

    async def recent(
        self, tenant_id: int = 1, limit: int = 10
    ) -> RecentOpportunityResp:
        """最近 ``limit`` 条商机，按 updated_at 倒序。

        LEFT JOIN crm_companies 获取企业名（企业被归档 / 删除时为 NULL）。
        """
        stmt = (
            select(
                Opportunity.id,
                Opportunity.name,
                Opportunity.stage,
                Opportunity.status,
                Opportunity.estimated_amount,
                Opportunity.owner_id,
                Opportunity.company_id,
                Company.name.label("company_name"),
                Opportunity.expected_close_date,
                Opportunity.updated_at,
                Opportunity.won_at,
            )
            .outerjoin(Company, Company.id == Opportunity.company_id)
            .where(Opportunity.tenant_id == tenant_id)
            .order_by(Opportunity.updated_at.desc(), Opportunity.id.desc())
            .limit(limit)
        )
        rows = (await self.db.execute(stmt)).all()
        items: List[RecentOpportunityItem] = []
        for (
            oid,
            name,
            stage,
            status,
            amt,
            owner_id,
            company_id,
            company_name,
            exp_date,
            updated_at,
            won_at,
        ) in rows:
            items.append(
                RecentOpportunityItem(
                    id=oid,
                    name=name,
                    stage=stage,
                    stage_label=STAGE_LABELS.get(stage, ""),
                    status=status,
                    estimated_amount=Decimal(amt) if amt is not None else None,
                    owner_id=owner_id,
                    company_id=company_id,
                    company_name=company_name,
                    expected_close_date=exp_date.isoformat() if exp_date else None,
                    updated_at=updated_at,
                    won_at=won_at,
                )
            )
        return RecentOpportunityResp(tenant_id=tenant_id, limit=limit, items=items)

    # ------------------------------------------------------------------ #
    # 6. Stage Distribution（阶段分布，饼图）
    # ------------------------------------------------------------------ #

    async def stage_distribution(self, tenant_id: int = 1) -> StageDistributionResp:
        """阶段分布：与 funnel 同样的统计，但用 stage_distribution 专用 schema。

        含 won / lost 终止态，用于前端饼图按阶段着色。
        """
        # 复用 funnel 的查询逻辑
        stmt = (
            select(
                Opportunity.stage,
                func.count(Opportunity.id).label("cnt"),
                func.coalesce(func.sum(Opportunity.estimated_amount), 0).label("amt"),
            )
            .where(Opportunity.tenant_id == tenant_id)
            .group_by(Opportunity.stage)
        )
        rows = (await self.db.execute(stmt)).all()
        by_stage: Dict[str, Tuple[int, Decimal]] = {
            stage: (cnt, Decimal(amt)) for stage, cnt, amt in rows
        }

        items: List[StageDistributionItem] = []
        total_count = 0
        total_amount = ZERO
        for stage in STAGE_DISPLAY_ORDER:
            cnt, amt = by_stage.get(stage, (0, ZERO))
            items.append(
                StageDistributionItem(
                    stage=stage,
                    stage_label=STAGE_LABELS.get(stage, ""),
                    count=cnt,
                    amount=amt,
                )
            )
            total_count += cnt
            total_amount += amt

        return StageDistributionResp(
            tenant_id=tenant_id,
            items=items,
            total_count=total_count,
            total_amount=total_amount,
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


__all__ = ["DashboardService"]
