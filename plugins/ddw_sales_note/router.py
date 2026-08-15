from __future__ import annotations

"""DDW 拜访与沟通记录插件 API 路由。

API 端点（8 个）：
  健康：GET  /health
  CRUD : POST /notes, GET /notes, GET /notes/{id}, PUT /notes/{id}
  删除：DELETE /notes/{id}                              （硬删除）
  商机：GET  /notes/by-opportunity/{opportunity_id}
  统计：GET  /notes/stats
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .schemas import (
    SalesNoteCreateReq,
    SalesNoteListResp,
    SalesNoteStatsResp,
    SalesNoteUpdateReq,
)
from .services import SalesNoteService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造拜访与沟通记录路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-sales-note",
        tags=["ddw-sales-note"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-sales-note", "version": "1.0.0", "status": "ok"}

    # -----------------------------------------------------------------------
    # CRUD
    # -----------------------------------------------------------------------

    @router.post("/notes", response_model=dict, status_code=201)
    async def create_note(data: SalesNoteCreateReq) -> dict:
        """新建拜访/沟通记录。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = SalesNoteService(db)
            try:
                return await svc.create(data)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

    @router.get("/notes", response_model=SalesNoteListResp)
    async def list_notes(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页条数"),
        user_id: Optional[int] = Query(None, description="按记录人筛选"),
        company_id: Optional[int] = Query(None, description="按企业筛选"),
        contact_id: Optional[int] = Query(None, description="按联系人筛选"),
        opportunity_id: Optional[int] = Query(None, description="按商机筛选"),
        note_type: Optional[str] = Query(None, description="按沟通类型筛选"),
        visit_date_from: Optional[datetime] = Query(None, description="沟通起始时间"),  # noqa: B008
        visit_date_to: Optional[datetime] = Query(None, description="沟通结束时间"),  # noqa: B008
    ) -> SalesNoteListResp:
        """记录列表（分页 + 多维筛选）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = SalesNoteService(db)
            return await svc.list(
                page=page,
                page_size=page_size,
                user_id=user_id,
                company_id=company_id,
                contact_id=contact_id,
                opportunity_id=opportunity_id,
                note_type=note_type,
                visit_date_from=visit_date_from,
                visit_date_to=visit_date_to,
            )

    @router.get("/notes/stats", response_model=SalesNoteStatsResp)
    async def note_stats() -> SalesNoteStatsResp:
        """记录统计概览。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = SalesNoteService(db)
            return await svc.stats()

    @router.get("/notes/by-opportunity/{opportunity_id}", response_model=list)
    async def list_notes_by_opportunity(opportunity_id: int) -> list:
        """某商机下的所有沟通记录。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = SalesNoteService(db)
            return await svc.list_by_opportunity(opportunity_id)

    @router.get("/notes/{note_id}", response_model=dict)
    async def get_note(note_id: int) -> dict:
        """记录详情。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = SalesNoteService(db)
            result = await svc.get(note_id)
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"sales note {note_id} not found",
                )
            return result

    @router.put("/notes/{note_id}", response_model=dict)
    async def update_note(note_id: int, data: SalesNoteUpdateReq) -> dict:
        """更新记录。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = SalesNoteService(db)
            try:
                result = await svc.update(note_id, data)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"sales note {note_id} not found",
                )
            return result

    @router.delete("/notes/{note_id}", response_model=dict)
    async def delete_note(note_id: int) -> dict:
        """硬删除记录（任务规范明确 DELETE 走真删除）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = SalesNoteService(db)
            ok = await svc.delete(note_id)
            if not ok:
                raise HTTPException(
                    status_code=404,
                    detail=f"sales note {note_id} not found",
                )
            return {"deleted": True, "id": note_id}

    return router


__all__ = ["build_router"]
