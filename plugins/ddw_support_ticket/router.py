from __future__ import annotations

"""DDW 售后工单插件 API 路由。

API 端点（9 个）：
  健康检查：GET  /health
  工单 CRUD ：POST /tickets, GET /tickets, GET /tickets/stats
            GET /tickets/{id}, PUT /tickets/{id}
  状态机  ：POST /tickets/{id}/assign
            POST /tickets/{id}/start
            POST /tickets/{id}/resolve
            POST /tickets/{id}/close

注意：stats 必须注册在 {id} 之前，否则 FastAPI 会把 "stats" 解析为 id。
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .schemas import (
    TicketAssignReq,
    TicketCreateReq,
    TicketListResp,
    TicketResolveReq,
    TicketStatsResp,
    TicketUpdateReq,
)
from .services import SupportTicketService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造售后工单路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-support-ticket",
        tags=["ddw-support-ticket"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-support-ticket", "version": "1.0.0", "status": "ok"}

    # -----------------------------------------------------------------------
    # 工单 CRUD —— 静态路径必须先于 {id}
    # -----------------------------------------------------------------------

    @router.post("/tickets", response_model=dict, status_code=201)
    async def create_ticket(data: TicketCreateReq) -> dict:
        """新建工单（状态默认 open，自动生成单号 TKT-YYYYMMDD-NNN）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = SupportTicketService(db)
                try:
                    return await svc.create(data)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))

    @router.get("/tickets", response_model=TicketListResp)
    async def list_tickets(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页条数"),
        company_id: Optional[int] = Query(None, description="按关联企业 ID 筛选"),
        instance_id: Optional[int] = Query(None, description="按关联实例 ID 筛选"),
        category: Optional[str] = Query(
            None, description="分类筛选（bug/feature/question/complaint/other）"
        ),
        priority: Optional[str] = Query(
            None, description="优先级筛选（low/normal/high/urgent）"
        ),
        assigned_to: Optional[int] = Query(None, description="按处理人 ID 筛选"),
        status: Optional[str] = Query(
            None, description="状态筛选（open/in_progress/resolved/closed）"
        ),
    ) -> TicketListResp:
        """工单列表（分页 + 多维筛选）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = SupportTicketService(db)
                return await svc.list(
                    page=page,
                    page_size=page_size,
                    company_id=company_id,
                    instance_id=instance_id,
                    category=category,
                    priority=priority,
                    assigned_to=assigned_to,
                    status=status,
                )

    # -----------------------------------------------------------------------
    # 统计（必须注册在 /tickets/{id} 之前）
    # -----------------------------------------------------------------------

    @router.get("/tickets/stats", response_model=TicketStatsResp)
    async def ticket_stats() -> TicketStatsResp:
        """工单统计概览。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = SupportTicketService(db)
                return await svc.stats()

    # -----------------------------------------------------------------------
    # 详情 / 更新
    # -----------------------------------------------------------------------

    @router.get("/tickets/{ticket_id}", response_model=dict)
    async def get_ticket(ticket_id: int) -> dict:
        """工单详情。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = SupportTicketService(db)
                result = await svc.get(ticket_id)
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"ticket {ticket_id} not found",
                    )
                return result

    @router.put("/tickets/{ticket_id}", response_model=dict)
    async def update_ticket(ticket_id: int, data: TicketUpdateReq) -> dict:
        """更新工单（status 不在本端点，单独走状态机）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = SupportTicketService(db)
                try:
                    result = await svc.update(ticket_id, data)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"ticket {ticket_id} not found",
                    )
                return result

    # -----------------------------------------------------------------------
    # 状态机迁移
    # -----------------------------------------------------------------------

    @router.post("/tickets/{ticket_id}/assign", response_model=dict)
    async def assign_ticket(ticket_id: int, data: TicketAssignReq) -> dict:
        """分配处理人（任意状态可改，不影响 status）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = SupportTicketService(db)
                result = await svc.assign(ticket_id, data)
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"ticket {ticket_id} not found",
                    )
                return result

    @router.post("/tickets/{ticket_id}/start", response_model=dict)
    async def start_ticket(ticket_id: int) -> dict:
        """开始处理（open → in_progress）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = SupportTicketService(db)
                try:
                    result = await svc.start(ticket_id)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"ticket {ticket_id} not found",
                    )
                return result

    @router.post("/tickets/{ticket_id}/resolve", response_model=dict)
    async def resolve_ticket(ticket_id: int, data: TicketResolveReq) -> dict:
        """解决工单（in_progress → resolved, resolution 必填, resolved_at=now）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = SupportTicketService(db)
                try:
                    result = await svc.resolve(ticket_id, data)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"ticket {ticket_id} not found",
                    )
                return result

    @router.post("/tickets/{ticket_id}/close", response_model=dict)
    async def close_ticket(ticket_id: int) -> dict:
        """关闭工单（resolved → closed）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = SupportTicketService(db)
                try:
                    result = await svc.close(ticket_id)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"ticket {ticket_id} not found",
                    )
                return result

    return router


__all__ = ["build_router"]
