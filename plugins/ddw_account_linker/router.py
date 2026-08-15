from __future__ import annotations

from typing import Optional

"""DDW 账号/租户/实例映射插件 API 路由。

API 端点（6 + 1 health = 7 个）：
  健康：  GET  /health
  新建：  POST /account-links
  列表：  GET  /account-links                     （分页 + 筛选：company/link_type/status）
  统计：  GET  /account-links/stats               （必须在 /{id} 之前注册）
  按企：  GET  /account-links/by-company/{cid}   （必须在 /{id} 之前注册）
  详情：  GET  /account-links/{id}
  软删：  DELETE /account-links/{id}              （status=inactive）
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .schemas import (
    AccountLinkCreateReq,
    AccountLinkListResp,
    AccountLinkStatsResp,
)
from .services import AccountLinkService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造账号/租户/实例映射路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-account-linker",
        tags=["ddw-account-linker"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-account-linker", "version": "1.0.0", "status": "ok"}

    # -----------------------------------------------------------------------
    # 新建账号链接
    # -----------------------------------------------------------------------
    @router.post("/account-links", response_model=dict, status_code=201)
    async def create_account_link(data: AccountLinkCreateReq) -> dict:
        """新建账号链接。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = AccountLinkService(db)
            try:
                return await svc.create(data)
            except ValueError as e:
                raise HTTPException(status_code=409, detail=str(e))

    # -----------------------------------------------------------------------
    # 列表（分页 + 多维筛选）
    # -----------------------------------------------------------------------
    @router.get("/account-links", response_model=AccountLinkListResp)
    async def list_account_links(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页条数"),
        company_id: Optional[int] = Query(None, description="按企业 ID 筛选"),
        link_type: Optional[str] = Query(
            None, description="链接类型：user / saas_tenant / on_premise_instance"
        ),
        status: Optional[str] = Query(None, description="状态：active / inactive"),
    ) -> AccountLinkListResp:
        """账号链接列表（分页 + 筛选：company/link_type/status）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = AccountLinkService(db)
            return await svc.list(
                page=page,
                page_size=page_size,
                company_id=company_id,
                link_type=link_type,
                status=status,
            )

    # -----------------------------------------------------------------------
    # 统计概览（必须在 /account-links/{id} 之前定义，否则 "stats" 会被解析为 {id}）
    # -----------------------------------------------------------------------
    @router.get("/account-links/stats", response_model=AccountLinkStatsResp)
    async def account_link_stats() -> AccountLinkStatsResp:
        """账号链接统计概览（total/active/inactive + by_link_type）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = AccountLinkService(db)
            return await svc.stats()

    # -----------------------------------------------------------------------
    # 按企业获取所有链接（必须在 /account-links/{id} 之前定义）
    # -----------------------------------------------------------------------
    @router.get("/account-links/by-company/{company_id}", response_model=list)
    async def get_account_links_by_company(company_id: int) -> list:
        """获取某企业的所有账号链接（不区分状态）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = AccountLinkService(db)
            return await svc.get_by_company(company_id)

    # -----------------------------------------------------------------------
    # 详情
    # -----------------------------------------------------------------------
    @router.get("/account-links/{link_id}", response_model=dict)
    async def get_account_link(link_id: int) -> dict:
        """账号链接详情。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = AccountLinkService(db)
            result = await svc.get(link_id)
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"account_link {link_id} not found",
                )
            return result

    # -----------------------------------------------------------------------
    # 软删除（停用）
    # -----------------------------------------------------------------------
    @router.delete("/account-links/{link_id}", response_model=dict)
    async def deactivate_account_link(link_id: int) -> dict:
        """停用账号链接（软删除：status=inactive）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = AccountLinkService(db)
            result = await svc.deactivate(link_id)
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"account_link {link_id} not found",
                )
            return result

    return router


__all__ = ["build_router"]
