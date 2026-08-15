from __future__ import annotations

"""DDW 联系人管理插件 API 路由。

API 端点（9 个）：
  健康：GET  /health
  CRUD : POST /contacts, GET /contacts, GET /contacts/{id}, PUT /contacts/{id}
  删除：DELETE /contacts/{id}              （硬删除）
  搜索：GET /contacts/search?q=
  企业：GET /contacts/by-company/{company_id}
  统计：GET /contacts/stats
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .schemas import (
    ContactCreateReq,
    ContactListResp,
    ContactStatsResp,
    ContactUpdateReq,
)
from .services import ContactService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造联系人管理路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-contact-hub",
        tags=["ddw-contact-hub"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-contact-hub", "version": "1.0.0", "status": "ok"}

    # -----------------------------------------------------------------------
    # 联系人 CRUD
    # -----------------------------------------------------------------------

    @router.post("/contacts", response_model=dict, status_code=201)
    async def create_contact(data: ContactCreateReq) -> dict:
        """新建联系人。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ContactService(db)
                try:
                    return await svc.create(data)
                except ValueError as e:
                    raise HTTPException(status_code=409, detail=str(e))

    @router.get("/contacts", response_model=ContactListResp)
    async def list_contacts(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页条数"),
        search: Optional[str] = Query(
            None, description="模糊搜索（姓名/手机/邮箱/职位/部门）"
        ),
        status: Optional[str] = Query(
            None, description="状态筛选（active/inactive/archived）"
        ),
        company_id: Optional[int] = Query(None, description="按所属企业筛选"),
        is_primary: Optional[bool] = Query(None, description="仅看主联系人"),
        tag: Optional[str] = Query(None, description="按标签筛选"),
        group: Optional[str] = Query(None, description="按分组筛选"),
    ) -> ContactListResp:
        """联系人列表（分页 + 筛选 + 搜索）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ContactService(db)
                return await svc.list(
                    page=page,
                    page_size=page_size,
                    search=search,
                    status=status,
                    company_id=company_id,
                    is_primary=is_primary,
                    tag=tag,
                    group=group,
                )

    @router.get("/contacts/search", response_model=list)
    async def search_contacts(
        q: str = Query(..., min_length=1, description="搜索关键词"),
        limit: int = Query(20, ge=1, le=50),
    ) -> list:
        """按姓名/手机/邮箱搜索（autocomplete）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ContactService(db)
                return await svc.search(q=q, limit=limit)

    @router.get("/contacts/stats", response_model=ContactStatsResp)
    async def contact_stats() -> ContactStatsResp:
        """联系人统计概览。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ContactService(db)
                return await svc.stats()

    @router.get("/contacts/by-company/{company_id}", response_model=list)
    async def list_contacts_by_company(company_id: int) -> list:
        """某企业所有联系人。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ContactService(db)
                return await svc.list_by_company(company_id)

    @router.get("/contacts/{contact_id}", response_model=dict)
    async def get_contact(contact_id: int) -> dict:
        """联系人详情。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ContactService(db)
                result = await svc.get(contact_id)
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"contact {contact_id} not found",
                    )
                return result

    @router.put("/contacts/{contact_id}", response_model=dict)
    async def update_contact(contact_id: int, data: ContactUpdateReq) -> dict:
        """更新联系人。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ContactService(db)
                result = await svc.update(contact_id, data)
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"contact {contact_id} not found",
                    )
                return result

    @router.delete("/contacts/{contact_id}", response_model=dict)
    async def delete_contact(contact_id: int) -> dict:
        """硬删除联系人（任务规范明确走真删除）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ContactService(db)
                ok = await svc.delete(contact_id)
                if not ok:
                    raise HTTPException(
                        status_code=404,
                        detail=f"contact {contact_id} not found",
                    )
                return {"deleted": True, "id": contact_id}

    return router


__all__ = ["build_router"]
