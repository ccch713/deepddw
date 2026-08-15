from __future__ import annotations

"""DDW 企业主体管理插件 API 路由。

API 端点（8 个）：
  企业：POST /companies, GET /companies, GET /companies/{id}, PUT /companies/{id}
  归档：DELETE /companies/{id}
  搜索：GET /companies/search?q=
  统计：GET /companies/stats
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .schemas import (
    CompanyCreateReq,
    CompanyListResp,
    CompanyStatsResp,
    CompanyUpdateReq,
)
from .services import CompanyService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造企业主体管理路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-company-profile",
        tags=["ddw-company-profile"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-company-profile", "version": "1.0.0", "status": "ok"}

    # -----------------------------------------------------------------------
    # 企业 CRUD
    # -----------------------------------------------------------------------

    @router.post("/companies", response_model=dict, status_code=201)
    async def create_company(data: CompanyCreateReq) -> dict:
        """新建企业。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = CompanyService(db)
                try:
                    return await svc.create(data)
                except ValueError as e:
                    raise HTTPException(status_code=409, detail=str(e))

    @router.get("/companies", response_model=CompanyListResp)
    async def list_companies(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页条数"),
        search: Optional[str] = Query(
            None, description="模糊搜索（名称/简称/信用代码/法人）"
        ),
        status: Optional[str] = Query(
            None, description="状态筛选（active/inactive/archived）"
        ),
        certification_status: Optional[str] = Query(None, description="认证状态"),
        company_type: Optional[str] = Query(None, description="企业类型"),
        industry: Optional[str] = Query(None, description="行业"),
    ) -> CompanyListResp:
        """企业列表（分页 + 筛选 + 搜索）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = CompanyService(db)
                return await svc.list(
                    page=page,
                    page_size=page_size,
                    search=search,
                    status=status,
                    certification_status=certification_status,
                    company_type=company_type,
                    industry=industry,
                )

    @router.get("/companies/search", response_model=list)
    async def search_companies(
        q: str = Query(..., min_length=1, description="搜索关键词"),
        limit: int = Query(20, ge=1, le=50),
    ) -> list:
        """按名称/信用代码搜索。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = CompanyService(db)
                return await svc.search(q=q, limit=limit)

    @router.get("/companies/stats", response_model=CompanyStatsResp)
    async def company_stats() -> CompanyStatsResp:
        """企业统计概览。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = CompanyService(db)
                return await svc.stats()

    @router.get("/companies/{company_id}", response_model=dict)
    async def get_company(company_id: int) -> dict:
        """企业详情。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = CompanyService(db)
                result = await svc.get(company_id)
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"company {company_id} not found",
                    )
                return result

    @router.put("/companies/{company_id}", response_model=dict)
    async def update_company(company_id: int, data: CompanyUpdateReq) -> dict:
        """更新企业。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = CompanyService(db)
                result = await svc.update(company_id, data)
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"company {company_id} not found",
                    )
                return result

    @router.delete("/companies/{company_id}", response_model=dict)
    async def archive_company(company_id: int) -> dict:
        """归档企业（软删除）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = CompanyService(db)
                result = await svc.archive(company_id)
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"company {company_id} not found",
                    )
                return result

    return router


__all__ = ["build_router"]
