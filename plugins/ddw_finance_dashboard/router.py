from __future__ import annotations

"""DDW 财务看板插件 API 路由。

API 端点（5 个）：
  健康： GET  /health
  总览： GET  /dashboard/overview
  逾期： GET  /dashboard/overdue
  趋势： GET  /dashboard/trend
  统计： GET  /dashboard/stats
"""

import logging

from fastapi import APIRouter, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .schemas import (
    OverdueResp,
    OverviewResp,
    StatsResp,
    TrendResp,
)
from .services import DashboardService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造财务看板路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-finance-dashboard",
        tags=["ddw-finance-dashboard"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-finance-dashboard", "version": "1.0.0", "status": "ok"}

    # -----------------------------------------------------------------------
    # 总览
    # -----------------------------------------------------------------------
    @router.get("/dashboard/overview", response_model=OverviewResp)
    async def dashboard_overview(
        tenant_id: int = Query(1, ge=1, description="租户 ID"),
    ) -> OverviewResp:
        """总览：合同 / 应收 / 实收 / 逾期 四维度。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = DashboardService(db)
                return await svc.overview(tenant_id=tenant_id)

    # -----------------------------------------------------------------------
    # 逾期列表
    # -----------------------------------------------------------------------
    @router.get("/dashboard/overdue", response_model=OverdueResp)
    async def dashboard_overdue(
        tenant_id: int = Query(1, ge=1, description="租户 ID"),
        limit: int = Query(100, ge=1, le=500, description="返回条数上限"),
    ) -> OverdueResp:
        """逾期列表：按 (amount - paid_amount) 降序的 top N。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = DashboardService(db)
                return await svc.overdue(tenant_id=tenant_id, limit=limit)

    # -----------------------------------------------------------------------
    # 趋势
    # -----------------------------------------------------------------------
    @router.get("/dashboard/trend", response_model=TrendResp)
    async def dashboard_trend(
        tenant_id: int = Query(1, ge=1, description="租户 ID"),
        months: int = Query(12, ge=1, le=36, description="回看月数（1-36）"),
    ) -> TrendResp:
        """趋势：最近 N 月（默认 12）的应收金额 + 实收金额。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = DashboardService(db)
                return await svc.trend(tenant_id=tenant_id, months=months)

    # -----------------------------------------------------------------------
    # 财务统计
    # -----------------------------------------------------------------------
    @router.get("/dashboard/stats", response_model=StatsResp)
    async def dashboard_stats(
        tenant_id: int = Query(1, ge=1, description="租户 ID"),
    ) -> StatsResp:
        """财务统计：按合同/应收/实收状态分布 + 按企业未收金额 top 50。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = DashboardService(db)
                return await svc.stats(tenant_id=tenant_id)

    return router


__all__ = ["build_router"]
