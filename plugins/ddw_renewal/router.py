from __future__ import annotations

"""DDW 续费与预警插件 API 路由。

API 端点（5 个）：
  健康：       GET  /health
  即将到期：   GET  /renewal/expiring?days=30
  已逾期：     GET  /renewal/overdue
  续费报价：   POST /renewal/quote
  续费统计：   GET  /renewal/stats
"""

import logging

from fastapi import APIRouter, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .schemas import (
    ExpiringResp,
    OverdueResp,
    QuoteReq,
    QuoteResp,
    RenewalStatsResp,
)
from .services import RenewalService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造续费预警路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-renewal",
        tags=["ddw-renewal"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-renewal", "version": "1.0.0", "status": "ok"}

    # -----------------------------------------------------------------------
    # 即将到期
    # -----------------------------------------------------------------------
    @router.get("/renewal/expiring", response_model=ExpiringResp)
    async def renewal_expiring(
        tenant_id: int = Query(1, ge=1, description="租户 ID"),
        days: int = Query(
            30,
            ge=1,
            le=365,
            description="到期窗口（天），常见 30 / 60 / 90",
        ),
    ) -> ExpiringResp:
        """即将到期许可证列表：status=active 且 ``today <= valid_to <= today + days``。

        按 valid_to 升序（最近到期的在最前），LEFT JOIN crm_companies 拿企业名。
        """
        async with session_scope() as db, bypass_tenant_filter():
            svc = RenewalService(db)
            return await svc.expiring(tenant_id=tenant_id, days=days)

    # -----------------------------------------------------------------------
    # 已逾期
    # -----------------------------------------------------------------------
    @router.get("/renewal/overdue", response_model=OverdueResp)
    async def renewal_overdue(
        tenant_id: int = Query(1, ge=1, description="租户 ID"),
    ) -> OverdueResp:
        """已逾期许可证列表：status IN (active, expired) 且 valid_to < today。

        按 valid_to 升序（最早逾期的在最前）。
        """
        async with session_scope() as db, bypass_tenant_filter():
            svc = RenewalService(db)
            return await svc.overdue(tenant_id=tenant_id)

    # -----------------------------------------------------------------------
    # 续费报价
    # -----------------------------------------------------------------------
    @router.post("/renewal/quote", response_model=QuoteResp)
    async def renewal_quote(req: QuoteReq) -> QuoteResp:
        """生成续费报价估算。

        - 入参 ``license_id`` 必填
        - ``renewal_unit_days`` 可选；None 时取上次 license 时长，否则 365
        - 估算金额 = 历史合同单日单价 * 续费天数；无历史 → 0（仅占位）

        业务异常：
        - 404-like：license 不存在 → ValueError
        - 400-like：license revoked / renewed → ValueError
        """
        async with session_scope() as db, bypass_tenant_filter():
            svc = RenewalService(db)
            return await svc.quote(
                tenant_id=req.tenant_id if req.tenant_id else 1,
                license_id=req.license_id,
                renewal_unit_days=req.renewal_unit_days,
            )

    # -----------------------------------------------------------------------
    # 续费统计
    # -----------------------------------------------------------------------
    @router.get("/renewal/stats", response_model=RenewalStatsResp)
    async def renewal_stats(
        tenant_id: int = Query(1, ge=1, description="租户 ID"),
    ) -> RenewalStatsResp:
        """续费统计概览：active / overdue / renewed_total / 续费率 + 30/60/90 窗口。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = RenewalService(db)
            return await svc.stats(tenant_id=tenant_id)

    return router


__all__ = ["build_router"]
