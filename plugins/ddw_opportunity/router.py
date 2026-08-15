from __future__ import annotations

"""DDW 商机管理插件 API 路由。

API 端点（11 个）：
  健康：GET /health
  CRUD：POST /opportunities, GET /opportunities, GET /opportunities/{id},
        PUT /opportunities/{id}, DELETE /opportunities/{id}
  阶段：PUT /opportunities/{id}/stage
  成交/丢单：POST /opportunities/{id}/win, POST /opportunities/{id}/lose
  统计：GET /opportunities/funnel, GET /opportunities/stats

注意：funnel / stats 必须注册在 {id} 之前，否则 FastAPI 会把 "funnel" 解析为 id。
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .schemas import (
    MarkLostReq,
    OpportunityCreateReq,
    OpportunityFunnelResp,
    OpportunityListResp,
    OpportunityStatsResp,
    OpportunityUpdateReq,
    StageUpdateReq,
)
from .services import OpportunityService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造商机管理路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-opportunity",
        tags=["ddw-opportunity"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-opportunity", "version": "1.0.0", "status": "ok"}

    # -----------------------------------------------------------------------
    # 商机 CRUD —— 静态路径必须先于 {id}
    # -----------------------------------------------------------------------

    @router.post("/opportunities", response_model=dict, status_code=201)
    async def create_opportunity(data: OpportunityCreateReq) -> dict:
        """新建商机。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = OpportunityService(db)
                try:
                    return await svc.create(data)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))

    @router.get("/opportunities", response_model=OpportunityListResp)
    async def list_opportunities(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页条数"),
        search: Optional[str] = Query(None, description="模糊搜索（按商机名称）"),
        owner_id: Optional[int] = Query(None, description="按负责人筛选"),
        stage: Optional[str] = Query(None, description="按阶段筛选"),
        status: Optional[str] = Query(
            None, description="按状态筛选（open/won/lost/closed）"
        ),
        company_id: Optional[int] = Query(None, description="按关联企业筛选"),
    ) -> OpportunityListResp:
        """商机列表（分页 + 筛选 + 搜索）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = OpportunityService(db)
                return await svc.list(
                    page=page,
                    page_size=page_size,
                    search=search,
                    owner_id=owner_id,
                    stage=stage,
                    status=status,
                    company_id=company_id,
                )

    # -----------------------------------------------------------------------
    # 统计（必须注册在 /opportunities/{id} 之前）
    # -----------------------------------------------------------------------

    @router.get("/opportunities/funnel", response_model=OpportunityFunnelResp)
    async def opportunity_funnel() -> OpportunityFunnelResp:
        """商机漏斗统计（按 stage 分组，含 count + total_amount）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = OpportunityService(db)
                return await svc.funnel()

    @router.get("/opportunities/stats", response_model=OpportunityStatsResp)
    async def opportunity_stats() -> OpportunityStatsResp:
        """商机统计概览。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = OpportunityService(db)
                return await svc.stats()

    # -----------------------------------------------------------------------
    # 详情 / 更新 / 关闭
    # -----------------------------------------------------------------------

    @router.get("/opportunities/{opp_id}", response_model=dict)
    async def get_opportunity(opp_id: int) -> dict:
        """商机详情。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = OpportunityService(db)
                result = await svc.get(opp_id)
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"opportunity {opp_id} not found",
                    )
                return result

    @router.put("/opportunities/{opp_id}", response_model=dict)
    async def update_opportunity(
        opp_id: int, data: OpportunityUpdateReq
    ) -> dict:
        """更新商机。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = OpportunityService(db)
                result = await svc.update(opp_id, data)
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"opportunity {opp_id} not found",
                    )
                return result

    @router.delete("/opportunities/{opp_id}", response_model=dict)
    async def close_opportunity(opp_id: int) -> dict:
        """关闭商机（status=closed）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = OpportunityService(db)
                result = await svc.close(opp_id)
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"opportunity {opp_id} not found",
                    )
                return result

    # -----------------------------------------------------------------------
    # 阶段 / 成交 / 丢单
    # -----------------------------------------------------------------------

    @router.put("/opportunities/{opp_id}/stage", response_model=dict)
    async def update_opportunity_stage(
        opp_id: int, data: StageUpdateReq
    ) -> dict:
        """更新阶段（自动同步 probability）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = OpportunityService(db)
                try:
                    result = await svc.update_stage(opp_id, data)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"opportunity {opp_id} not found",
                    )
                return result

    @router.post("/opportunities/{opp_id}/win", response_model=dict)
    async def mark_opportunity_won(opp_id: int) -> dict:
        """标记成交（status=won, stage=won, won_at=now, probability=100）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = OpportunityService(db)
                result = await svc.mark_won(opp_id)
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"opportunity {opp_id} not found",
                    )
                return result

    @router.post("/opportunities/{opp_id}/lose", response_model=dict)
    async def mark_opportunity_lost(
        opp_id: int, data: MarkLostReq
    ) -> dict:
        """标记丢单（status=lost, stage=lost, lost_reason 必填）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = OpportunityService(db)
                result = await svc.mark_lost(opp_id, data)
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"opportunity {opp_id} not found",
                    )
                return result

    return router


__all__ = ["build_router"]
