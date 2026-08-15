from __future__ import annotations

"""DDW 销售看板插件 API 路由。

API 端点（7 个）：
  健康： GET  /health
  总览： GET  /dashboard/overview
  漏斗： GET  /dashboard/funnel
  趋势： GET  /dashboard/trend
  排行： GET  /dashboard/ranking
  最近： GET  /dashboard/recent
  分布： GET  /dashboard/stage-distribution
"""

import logging

from fastapi import APIRouter, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .schemas import (
    FunnelResp,
    OverviewResp,
    RankingResp,
    RecentOpportunityResp,
    StageDistributionResp,
    TrendResp,
)
from .services import DashboardService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造销售看板路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-sales-dashboard",
        tags=["ddw-sales-dashboard"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-sales-dashboard", "version": "1.0.0", "status": "ok"}

    # -----------------------------------------------------------------------
    # 总览
    # -----------------------------------------------------------------------
    @router.get("/dashboard/overview", response_model=OverviewResp)
    async def dashboard_overview(
        tenant_id: int = Query(1, ge=1, description="租户 ID"),
    ) -> OverviewResp:
        """总览：企业 / 联系人 / 商机 / 报价 / 金额 / 成交客户数。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = DashboardService(db)
                return await svc.overview(tenant_id=tenant_id)

    # -----------------------------------------------------------------------
    # 漏斗
    # -----------------------------------------------------------------------
    @router.get("/dashboard/funnel", response_model=FunnelResp)
    async def dashboard_funnel(
        tenant_id: int = Query(1, ge=1, description="租户 ID"),
    ) -> FunnelResp:
        """漏斗：按商机阶段分组（含已成交 / 丢单的终止态）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = DashboardService(db)
                return await svc.funnel(tenant_id=tenant_id)

    # -----------------------------------------------------------------------
    # 趋势
    # -----------------------------------------------------------------------
    @router.get("/dashboard/trend", response_model=TrendResp)
    async def dashboard_trend(
        tenant_id: int = Query(1, ge=1, description="租户 ID"),
        months: int = Query(12, ge=1, le=36, description="回看月数（1-36）"),
    ) -> TrendResp:
        """趋势：最近 N 月（默认 12）的新增商机数 / 金额 / 成交金额。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = DashboardService(db)
                return await svc.trend(tenant_id=tenant_id, months=months)

    # -----------------------------------------------------------------------
    # 销售排行
    # -----------------------------------------------------------------------
    @router.get("/dashboard/ranking", response_model=RankingResp)
    async def dashboard_ranking(
        tenant_id: int = Query(1, ge=1, description="租户 ID"),
    ) -> RankingResp:
        """销售排行：按 owner_id 聚合，按 estimated_amount 降序。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = DashboardService(db)
                return await svc.ranking(tenant_id=tenant_id)

    # -----------------------------------------------------------------------
    # 最近商机
    # -----------------------------------------------------------------------
    @router.get("/dashboard/recent", response_model=RecentOpportunityResp)
    async def dashboard_recent(
        tenant_id: int = Query(1, ge=1, description="租户 ID"),
        limit: int = Query(10, ge=1, le=50, description="返回条数"),
    ) -> RecentOpportunityResp:
        """最近商机：按 updated_at 倒序的 N 条商机（默认 10）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = DashboardService(db)
                return await svc.recent(tenant_id=tenant_id, limit=limit)

    # -----------------------------------------------------------------------
    # 阶段分布
    # -----------------------------------------------------------------------
    @router.get("/dashboard/stage-distribution", response_model=StageDistributionResp)
    async def dashboard_stage_distribution(
        tenant_id: int = Query(1, ge=1, description="租户 ID"),
    ) -> StageDistributionResp:
        """阶段分布：用于前端饼图 / 环图的数据。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = DashboardService(db)
                return await svc.stage_distribution(tenant_id=tenant_id)

    return router


__all__ = ["build_router"]
