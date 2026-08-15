from __future__ import annotations

"""DDW 客户报备与归属插件 API 路由。

API 端点（8 个）：
  健康检查：GET   /health
  报备    ：POST  /claims
            GET   /claims
            GET   /claims/conflict
            GET   /claims/stats
            GET   /claims/{id}
            PUT   /claims/{id}
            POST  /claims/{id}/release

注意：/conflict 与 /stats 必须注册在 /{id} 之前，否则 FastAPI 会把
"conflict" / "stats" 解析为 id。
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .schemas import (
    LeadClaimConflictResp,
    LeadClaimCreateReq,
    LeadClaimListResp,
    LeadClaimStatsResp,
    LeadClaimUpdateReq,
    ReleaseClaimReq,
)
from .services import LeadClaimService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造客户报备与归属路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-lead-claim",
        tags=["ddw-lead-claim"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-lead-claim", "version": "1.0.0", "status": "ok"}

    # -----------------------------------------------------------------------
    # 报备 CRUD —— 静态路径必须先于 /{id}
    # -----------------------------------------------------------------------

    @router.post("/claims", response_model=dict, status_code=201)
    async def create_claim(data: LeadClaimCreateReq) -> dict:
        """新建报备。

        - 服务端按 ``claim_date + protection_days`` 自动计算 ``expire_at``
        - 同一 partner + company 已有 active 报备时拒绝（409）
        """
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = LeadClaimService(db)
                try:
                    return await svc.create(data)
                except ValueError as e:
                    raise HTTPException(status_code=409, detail=str(e))

    @router.get("/claims", response_model=LeadClaimListResp)
    async def list_claims(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页条数"),
        partner_id: Optional[int] = Query(None, description="按渠道/销售 ID 筛选"),
        company_id: Optional[int] = Query(None, description="按客户企业 ID 筛选"),
        status: Optional[str] = Query(
            None, description="按状态筛选（active/expired/won/lost/released）"
        ),
        expire_before: Optional[datetime] = Query(
            None, description="保护期截止 <= 该值（ISO 格式）"
        ),
        expire_after: Optional[datetime] = Query(
            None, description="保护期截止 >= 该值（ISO 格式）"
        ),
    ) -> LeadClaimListResp:
        """报备列表（分页 + 多维筛选；查询前自动标记过期）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = LeadClaimService(db)
                return await svc.list(
                    page=page,
                    page_size=page_size,
                    partner_id=partner_id,
                    company_id=company_id,
                    status=status,
                    expire_before=expire_before,
                    expire_after=expire_after,
                )

    # -----------------------------------------------------------------------
    # 专用端点：冲突查询 / 统计（必须在 /{id} 之前）
    # -----------------------------------------------------------------------

    @router.get("/claims/conflict", response_model=LeadClaimConflictResp)
    async def conflict_query(
        company_id: int = Query(..., ge=1, description="客户企业 ID"),
    ) -> LeadClaimConflictResp:
        """冲突查询：返回该企业的所有报备 + active 计数。

        用于销售/渠道在新建报备前检测该公司是否已被他人占位。
        """
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = LeadClaimService(db)
                return await svc.conflict(company_id=company_id)

    @router.get("/claims/stats", response_model=LeadClaimStatsResp)
    async def claim_stats() -> LeadClaimStatsResp:
        """报备统计概览。

        - 各状态计数
        - 按 partner 分组的 active 报备数
        """
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = LeadClaimService(db)
                return await svc.stats()

    # -----------------------------------------------------------------------
    # 详情 / 更新
    # -----------------------------------------------------------------------

    @router.get("/claims/{claim_id}", response_model=dict)
    async def get_claim(claim_id: int) -> dict:
        """报备详情（read 前自动标记过期）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = LeadClaimService(db)
                result = await svc.get(claim_id)
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"lead_claim {claim_id} not found",
                    )
                return result

    @router.put("/claims/{claim_id}", response_model=dict)
    async def update_claim(
        claim_id: int, data: LeadClaimUpdateReq
    ) -> dict:
        """更新报备（仅 active 状态可改）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = LeadClaimService(db)
                try:
                    result = await svc.update(claim_id, data)
                except ValueError as e:
                    raise HTTPException(status_code=409, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"lead_claim {claim_id} not found",
                    )
                return result

    # -----------------------------------------------------------------------
    # 释放
    # -----------------------------------------------------------------------

    @router.post("/claims/{claim_id}/release", response_model=dict)
    async def release_claim(
        claim_id: int, data: ReleaseClaimReq
    ) -> dict:
        """主动释放报备（status=released；记录 release_reason）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = LeadClaimService(db)
                try:
                    result = await svc.release(claim_id, data)
                except ValueError as e:
                    raise HTTPException(status_code=409, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"lead_claim {claim_id} not found",
                    )
                return result

    return router


__all__ = ["build_router"]
