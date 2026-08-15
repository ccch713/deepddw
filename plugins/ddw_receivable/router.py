from __future__ import annotations

"""DDW 应收管理插件 API 路由。

API 端点（8 个）：
  健康检查：GET  /health
  应收    ：POST /receivables
            GET  /receivables
            GET  /receivables/overdue
            GET  /receivables/stats
            GET  /receivables/{id}
            PUT  /receivables/{id}
  收款    ：POST /receivables/{id}/record-payment

注意：/overdue 与 /stats 必须注册在 /{id} 之前，否则 FastAPI 会把
"overdue" / "stats" 解析为 id。
"""

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .schemas import (
    ReceivableCreateReq,
    ReceivableListResp,
    ReceivableOverdueListResp,
    ReceivableStatsResp,
    ReceivableUpdateReq,
    RecordPaymentReq,
)
from .services import ReceivableService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造应收管理路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-receivable",
        tags=["ddw-receivable"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-receivable", "version": "1.0.0", "status": "ok"}

    # -----------------------------------------------------------------------
    # 应收 CRUD —— 静态路径必须先于 {id}
    # -----------------------------------------------------------------------

    @router.post("/receivables", response_model=dict, status_code=201)
    async def create_receivable(data: ReceivableCreateReq) -> dict:
        """新建应收。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ReceivableService(db)
                try:
                    return await svc.create(data)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))

    @router.get("/receivables", response_model=ReceivableListResp)
    async def list_receivables(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页条数"),
        company_id: Optional[int] = Query(None, description="按关联企业筛选"),
        order_id: Optional[int] = Query(None, description="按关联订单筛选"),
        contract_id: Optional[int] = Query(None, description="按关联合同筛选"),
        status: Optional[str] = Query(
            None, description="按状态筛选（pending/partial/paid/overdue）"
        ),
        due_before: Optional[date] = Query(None, description="应收日期 <= 该值"),
        due_after: Optional[date] = Query(None, description="应收日期 >= 该值"),
    ) -> ReceivableListResp:
        """应收列表（分页 + 多维筛选；查询前自动标记逾期）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ReceivableService(db)
                return await svc.list(
                    page=page,
                    page_size=page_size,
                    company_id=company_id,
                    order_id=order_id,
                    contract_id=contract_id,
                    status=status,
                    due_before=due_before,
                    due_after=due_after,
                )

    # -----------------------------------------------------------------------
    # 专用端点：逾期 / 统计（必须在 /{id} 之前）
    # -----------------------------------------------------------------------

    @router.get("/receivables/overdue", response_model=ReceivableOverdueListResp)
    async def list_overdue_receivables(
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
    ) -> ReceivableOverdueListResp:
        """逾期应收列表（专用端点）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ReceivableService(db)
                return await svc.overdue(page=page, page_size=page_size)

    @router.get("/receivables/stats", response_model=ReceivableStatsResp)
    async def receivable_stats() -> ReceivableStatsResp:
        """应收统计概览。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ReceivableService(db)
                return await svc.stats()

    # -----------------------------------------------------------------------
    # 详情 / 更新
    # -----------------------------------------------------------------------

    @router.get("/receivables/{receivable_id}", response_model=dict)
    async def get_receivable(receivable_id: int) -> dict:
        """应收详情。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ReceivableService(db)
                result = await svc.get(receivable_id)
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"receivable {receivable_id} not found",
                    )
                return result

    @router.put("/receivables/{receivable_id}", response_model=dict)
    async def update_receivable(
        receivable_id: int, data: ReceivableUpdateReq
    ) -> dict:
        """更新应收（仅 pending/overdue 状态可改）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ReceivableService(db)
                try:
                    result = await svc.update(receivable_id, data)
                except ValueError as e:
                    raise HTTPException(status_code=409, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"receivable {receivable_id} not found",
                    )
                return result

    # -----------------------------------------------------------------------
    # 收款
    # -----------------------------------------------------------------------

    @router.post("/receivables/{receivable_id}/record-payment", response_model=dict)
    async def record_payment(
        receivable_id: int, data: RecordPaymentReq
    ) -> dict:
        """记录收款（增量累加；自动重算 status）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ReceivableService(db)
                result = await svc.record_payment(receivable_id, data)
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"receivable {receivable_id} not found",
                    )
                return result

    return router


__all__ = ["build_router"]
