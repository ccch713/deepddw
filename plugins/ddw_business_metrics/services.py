"""DDW 业务指标仪表盘插件业务逻辑层。

纯只读聚合查询：
- 不创建新表
- 不调用 LLM
- 通过 SQLAlchemy 跨插件 query 现有 ORM 模型聚合
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Tuple

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wallet.models import RechargeOrder
from plugins.ddw_saas_billing.models import UsageLog
from plugins.ddw_lead_claim.models import LeadClaim
from plugins.ddw_opportunity.models import Opportunity
from plugins.ddw_order.models import Order

from .schemas import FunnelStage, MetricPoint, PluginUsage

logger = logging.getLogger(__name__)


class MetricsService:
    """业务指标聚合查询服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # 1. MRR（月经常性收入）
    # ------------------------------------------------------------------ #

    async def compute_mrr(
        self, tenant_id: int, months: int = 6
    ) -> List[MetricPoint]:
        """MRR 近 N 月趋势。

        当月 status='paid' 充值单金额合计（分），按月份分组。
        """
        stmt = (
            select(
                func.strftime("%Y-%m", RechargeOrder.paid_at).label("m"),
                func.coalesce(func.sum(RechargeOrder.amount_cents), 0).label("total"),
            )
            .where(
                RechargeOrder.status == "paid",
                RechargeOrder.tenant_id == str(tenant_id),
                RechargeOrder.paid_at.isnot(None),
            )
            .group_by("m")
            .order_by(text("m DESC"))
            .limit(months)
        )
        rows = (await self.db.execute(stmt)).all()
        # 倒序 → 正序
        rows = list(reversed(rows))
        return [
            MetricPoint(label=m, value=float(total_cents) / 100)
            for m, total_cents in rows
        ]

    # ------------------------------------------------------------------ #
    # 2. WAU（周活跃用户）
    # ------------------------------------------------------------------ #

    async def compute_wau(
        self, tenant_id: int, weeks: int = 8
    ) -> Tuple[int, List[MetricPoint]]:
        """WAU 近 N 周趋势。

        按 ISO 周分组，统计 distinct user_id。
        返回 (当前周 WAU, 趋势列表)。
        """
        now = datetime.utcnow()
        window_start = now - timedelta(weeks=weeks)

        stmt = (
            select(
                func.strftime("%Y-W%W", UsageLog.created_at).label("w"),
                func.count(func.distinct(UsageLog.user_id)).label("users"),
            )
            .where(
                UsageLog.tenant_id == tenant_id,
                UsageLog.created_at >= window_start,
            )
            .group_by("w")
            .order_by(text("w DESC"))
            .limit(weeks)
        )
        rows = (await self.db.execute(stmt)).all()
        rows = list(reversed(rows))

        current_wau = rows[-1][1] if rows else 0
        trend = [MetricPoint(label=w, value=float(users)) for w, users in rows]
        return current_wau, trend

    # ------------------------------------------------------------------ #
    # 3. 插件使用率 Top N
    # ------------------------------------------------------------------ #

    async def compute_plugins_top(
        self, tenant_id: int, limit: int = 10
    ) -> List[PluginUsage]:
        """插件使用率 Top N（按 event_type 分组的记录数）。"""
        stmt = (
            select(
                UsageLog.event_type,
                func.count(UsageLog.id).label("cnt"),
            )
            .where(UsageLog.tenant_id == tenant_id)
            .group_by(UsageLog.event_type)
            .order_by(text("cnt DESC"))
            .limit(limit)
        )
        rows = (await self.db.execute(stmt)).all()
        return [PluginUsage(event_type=et, count=c) for et, c in rows]

    # ------------------------------------------------------------------ #
    # 4. 转化漏斗
    # ------------------------------------------------------------------ #

    async def compute_funnel(self, tenant_id: int) -> List[FunnelStage]:
        """转化漏斗：线索 → 商机 → 订单各阶段数量。"""
        leads = (
            await self.db.execute(
                select(func.count(LeadClaim.id)).where(
                    LeadClaim.tenant_id == tenant_id
                )
            )
        ).scalar_one()

        opportunities = (
            await self.db.execute(
                select(func.count(Opportunity.id)).where(
                    Opportunity.tenant_id == tenant_id
                )
            )
        ).scalar_one()

        orders = (
            await self.db.execute(
                select(func.count(Order.id)).where(
                    Order.tenant_id == tenant_id
                )
            )
        ).scalar_one()

        return [
            FunnelStage(stage="leads", count=leads),
            FunnelStage(stage="opportunities", count=opportunities),
            FunnelStage(stage="orders", count=orders),
        ]

    # ------------------------------------------------------------------ #
    # 5. Token 消耗
    # ------------------------------------------------------------------ #

    async def compute_token_usage_7d(self, tenant_id: int) -> int:
        """近 7 天 tokens_used 合计。"""
        now = datetime.utcnow()
        window_start = now - timedelta(days=7)

        result = (
            await self.db.execute(
                select(func.coalesce(func.sum(UsageLog.tokens_used), 0)).where(
                    UsageLog.tenant_id == tenant_id,
                    UsageLog.created_at >= window_start,
                )
            )
        ).scalar_one()
        return int(result)

    # ------------------------------------------------------------------ #
    # 6. 总览（聚合以上指标）
    # ------------------------------------------------------------------ #

    async def summary(
        self,
        tenant_id: int,
        mrr_months: int = 6,
        wau_weeks: int = 8,
        plugins_top_limit: int = 10,
    ) -> dict:
        """业务指标总览。"""
        mrr_trend = await self.compute_mrr(tenant_id, months=mrr_months)
        current_mrr_cents = int(mrr_trend[-1].value * 100) if mrr_trend else 0

        current_wau, wau_trend = await self.compute_wau(tenant_id, weeks=wau_weeks)

        token_usage_7d = await self.compute_token_usage_7d(tenant_id)

        plugins_top = await self.compute_plugins_top(
            tenant_id, limit=plugins_top_limit
        )

        funnel = await self.compute_funnel(tenant_id)

        return {
            "mrr_cents": current_mrr_cents,
            "mrr_trend": mrr_trend,
            "wau": current_wau,
            "wau_trend": wau_trend,
            "token_usage_7d": token_usage_7d,
            "plugins_top": plugins_top,
            "funnel": funnel,
        }


__all__ = ["MetricsService"]
