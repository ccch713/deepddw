from __future__ import annotations

from typing import Optional

"""DDW 应收实收核销插件 API 路由。

API 端点（6 个）：
  健康检查：GET  /health
  匹配推荐：POST /reconciliation/match
  确认核销：POST /reconciliation/confirm
  取消核销：POST /reconciliation/cancel
  核销历史：GET  /reconciliation/history
  未核销汇总：GET /reconciliation/unmatched
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .schemas import (
    CancelReq,
    CancelResp,
    ConfirmReq,
    ConfirmResp,
    HistoryResp,
    MatchReq,
    MatchResp,
    UnmatchedSummaryResp,
)
from .services import ReconciliationService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造核销路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-reconciliation",
        tags=["ddw-reconciliation"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-reconciliation", "version": "1.0.0", "status": "ok"}

    # -----------------------------------------------------------------------
    # 1. 匹配推荐
    # -----------------------------------------------------------------------
    @router.post("/reconciliation/match", response_model=MatchResp)
    async def match_receivables(data: MatchReq) -> MatchResp:
        """按 payment_id 自动推荐可匹配的 receivable 列表（精确匹配：金额+公司）。

        返回 suggestions 列表，每条带 suggested_amount 与 confidence。
        """
        async with session_scope() as db, bypass_tenant_filter():
            svc = ReconciliationService(db)
            try:
                return await svc.match(data)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

    # -----------------------------------------------------------------------
    # 2. 确认核销（事务）
    # -----------------------------------------------------------------------
    @router.post("/reconciliation/confirm", response_model=ConfirmResp)
    async def confirm_reconciliation(data: ConfirmReq) -> ConfirmResp:
        """确认核销：事务内更新多个 receivable + 一个 payment 的 matched_amount / paid_amount。

        - 任何子操作失败 → 整体 rollback
        - 超付（> receivable.amount）默认拒绝（400）
        """
        async with session_scope() as db, bypass_tenant_filter():
            svc = ReconciliationService(db)
            try:
                return await svc.confirm(data)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

    # -----------------------------------------------------------------------
    # 3. 取消核销（事务）
    # -----------------------------------------------------------------------
    @router.post("/reconciliation/cancel", response_model=CancelResp)
    async def cancel_reconciliation(data: CancelReq) -> CancelResp:
        """取消核销：回退已核销金额。

        - 传 receivable_id：只回退该 (payment, receivable) 配对
        - 传 cancel_all=True：把该 payment 的所有配对一次性回退
        """
        async with session_scope() as db, bypass_tenant_filter():
            svc = ReconciliationService(db)
            try:
                return await svc.cancel(data)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

    # -----------------------------------------------------------------------
    # 4. 核销历史（从内存 _history 读取）
    # -----------------------------------------------------------------------
    @router.get("/reconciliation/history", response_model=HistoryResp)
    async def reconciliation_history(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(50, ge=1, le=200, description="每页条数"),
        payment_id: Optional[int] = Query(None, description="按 payment_id 过滤"),
        action: Optional[str] = Query(
            None, description="按动作过滤：confirm / cancel"
        ),
    ) -> HistoryResp:
        """核销历史（从内存读取，按 id 倒序）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = ReconciliationService(db)
            return await svc.history(
                page=page,
                page_size=page_size,
                payment_id=payment_id,
                action=action,
            )

    # -----------------------------------------------------------------------
    # 5. 未核销汇总
    # -----------------------------------------------------------------------
    @router.get("/reconciliation/unmatched", response_model=UnmatchedSummaryResp)
    async def unmatched_summary() -> UnmatchedSummaryResp:
        """未核销汇总：
        - payments：status=pending/partial 且 matched_amount < amount
        - receivables：status=pending/partial/overdue 且 paid_amount < amount
        """
        async with session_scope() as db, bypass_tenant_filter():
            svc = ReconciliationService(db)
            return await svc.unmatched()

    return router


__all__ = ["build_router"]
