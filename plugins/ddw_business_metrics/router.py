"""DDW 业务指标仪表盘插件 API 路由。

API 端点（5 个）：
  健康： GET  /health
  总览： GET  /summary
  MRR：  GET  /mrr?months=6
  WAU：  GET  /wau?weeks=8
  Top：  GET  /plugins-top?limit=10
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from core.auth.jwt import current_user
from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from . import VERSION
from .schemas import HealthResp, MetricPoint, MetricsSummary, PluginUsage
from .services import MetricsService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造业务指标仪表盘路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-business-metrics",
        tags=["ddw-business-metrics"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health", response_model=HealthResp)
    async def health() -> HealthResp:
        return HealthResp(status="ok", version=VERSION)

    # -----------------------------------------------------------------------
    # 总览
    # -----------------------------------------------------------------------
    @router.get("/summary", response_model=MetricsSummary)
    async def summary(
        user: dict = Depends(current_user),
    ) -> MetricsSummary:
        """总览：MRR / WAU / Token / 插件使用率 / 漏斗。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = MetricsService(db)
                tenant_id = int(user["tenant_id"])
                data = await svc.summary(tenant_id=tenant_id)
                return MetricsSummary(
                    mrr_cents=data["mrr_cents"],
                    mrr_trend=data["mrr_trend"],
                    wau=data["wau"],
                    wau_trend=data["wau_trend"],
                    token_usage_7d=data["token_usage_7d"],
                    plugins_top=data["plugins_top"],
                    funnel=data["funnel"],
                    as_of=datetime.now(timezone.utc).isoformat(),
                )

    # -----------------------------------------------------------------------
    # MRR 趋势
    # -----------------------------------------------------------------------
    @router.get("/mrr", response_model=list[MetricPoint])
    async def mrr_trend(
        user: dict = Depends(current_user),
        months: int = Query(6, ge=1, le=36, description="回看月数"),
    ) -> list[MetricPoint]:
        """MRR 近 N 月趋势。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = MetricsService(db)
                tenant_id = int(user["tenant_id"])
                return await svc.compute_mrr(tenant_id, months=months)

    # -----------------------------------------------------------------------
    # WAU 趋势
    # -----------------------------------------------------------------------
    @router.get("/wau", response_model=list[MetricPoint])
    async def wau_trend(
        user: dict = Depends(current_user),
        weeks: int = Query(8, ge=1, le=52, description="回看周数"),
    ) -> list[MetricPoint]:
        """WAU 近 N 周趋势。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = MetricsService(db)
                tenant_id = int(user["tenant_id"])
                _, trend = await svc.compute_wau(tenant_id, weeks=weeks)
                return trend

    # -----------------------------------------------------------------------
    # 插件使用率 Top
    # -----------------------------------------------------------------------
    @router.get("/plugins-top", response_model=list[PluginUsage])
    async def plugins_top(
        user: dict = Depends(current_user),
        limit: int = Query(10, ge=1, le=100, description="返回条数"),
    ) -> list[PluginUsage]:
        """插件使用率 Top N。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = MetricsService(db)
                tenant_id = int(user["tenant_id"])
                return await svc.compute_plugins_top(tenant_id, limit=limit)

    return router


__all__ = ["build_router"]
