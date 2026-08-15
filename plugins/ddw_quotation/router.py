from __future__ import annotations

"""DDW 报价单管理插件 API 路由。

API 端点：
  健康检查：GET  /health
  报价单  ：POST /quotations, GET /quotations, GET /quotations/stats
            GET /quotations/{id}, PUT /quotations/{id}, DELETE /quotations/{id}
  状态机  ：POST /quotations/{id}/send
            POST /quotations/{id}/accept
            POST /quotations/{id}/reject
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .schemas import (
    QuotationCreateReq,
    QuotationListResp,
    QuotationStatsResp,
    QuotationUpdateReq,
)
from .services import QuotationService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造报价单管理路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-quotation",
        tags=["ddw-quotation"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-quotation", "version": "1.0.0", "status": "ok"}

    # -----------------------------------------------------------------------
    # 报价单 CRUD
    # -----------------------------------------------------------------------

    @router.post("/quotations", response_model=dict, status_code=201)
    async def create_quotation(data: QuotationCreateReq) -> dict:
        """新建报价单（含明细列表）。

        - 服务端自动生成单号（QT-YYYYMMDD-NNN）
        - 服务端自动计算 total_amount / final_amount
        - 状态默认为 draft
        """
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = QuotationService(db)
                try:
                    return await svc.create(data)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))

    @router.get("/quotations", response_model=QuotationListResp)
    async def list_quotations(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页条数"),
        search: Optional[str] = Query(
            None, description="模糊搜索（单号 / 标题）"
        ),
        status: Optional[str] = Query(
            None, description="状态筛选（draft/sent/accepted/rejected/expired）"
        ),
        company_id: Optional[int] = Query(None, description="按关联企业 ID 筛选"),
    ) -> QuotationListResp:
        """报价单列表（分页 + 筛选 + 搜索）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = QuotationService(db)
                return await svc.list(
                    page=page,
                    page_size=page_size,
                    search=search,
                    status=status,
                    company_id=company_id,
                )

    @router.get("/quotations/stats", response_model=QuotationStatsResp)
    async def quotation_stats() -> QuotationStatsResp:
        """报价单统计概览。

        - 各状态计数
        - 所有报价单 final_amount 之和
        - 已接受报价单 final_amount 之和
        """
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = QuotationService(db)
                return await svc.stats()

    @router.get("/quotations/{quotation_id}", response_model=dict)
    async def get_quotation(quotation_id: int) -> dict:
        """报价单详情（含所有 items）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = QuotationService(db)
                result = await svc.get(quotation_id)
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"quotation {quotation_id} not found",
                    )
                return result

    @router.put("/quotations/{quotation_id}", response_model=dict)
    async def update_quotation(quotation_id: int, data: QuotationUpdateReq) -> dict:
        """更新报价单。

        - 字段级更新（model_dump(exclude_unset=True)）
        - 若 ``items`` 非 None：级联删除旧明细，重建新明细并重算金额
        - 若 ``items`` 为 None：保留明细
        """
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = QuotationService(db)
                try:
                    result = await svc.update(quotation_id, data)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"quotation {quotation_id} not found",
                    )
                return result

    @router.delete("/quotations/{quotation_id}", response_model=dict)
    async def delete_quotation(quotation_id: int) -> dict:
        """硬删除报价单（FK CASCADE 自动清理 items）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = QuotationService(db)
                ok = await svc.delete(quotation_id)
                if not ok:
                    raise HTTPException(
                        status_code=404,
                        detail=f"quotation {quotation_id} not found",
                    )
                return {"id": quotation_id, "deleted": True}

    # -----------------------------------------------------------------------
    # 状态机
    # -----------------------------------------------------------------------

    @router.post("/quotations/{quotation_id}/send", response_model=dict)
    async def send_quotation(quotation_id: int) -> dict:
        """标记已发送（status=draft → sent, sent_at=now）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = QuotationService(db)
                try:
                    result = await svc.mark_sent(quotation_id)
                except ValueError as e:
                    raise HTTPException(status_code=409, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"quotation {quotation_id} not found",
                    )
                return result

    @router.post("/quotations/{quotation_id}/accept", response_model=dict)
    async def accept_quotation(quotation_id: int) -> dict:
        """标记已接受（status=sent → accepted, accepted_at=now）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = QuotationService(db)
                try:
                    result = await svc.mark_accepted(quotation_id)
                except ValueError as e:
                    raise HTTPException(status_code=409, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"quotation {quotation_id} not found",
                    )
                return result

    @router.post("/quotations/{quotation_id}/reject", response_model=dict)
    async def reject_quotation(quotation_id: int) -> dict:
        """标记已拒绝（status=draft/sent → rejected, rejected_at=now）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = QuotationService(db)
                try:
                    result = await svc.mark_rejected(quotation_id)
                except ValueError as e:
                    raise HTTPException(status_code=409, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"quotation {quotation_id} not found",
                    )
                return result

    return router


__all__ = ["build_router"]
