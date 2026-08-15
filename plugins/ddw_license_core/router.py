from __future__ import annotations

from typing import Optional

"""DDW 许可证管理插件 API 路由。

API 端点（10 个）：
  健康检查：GET  /health
  许可证  ：POST /licenses
           GET  /licenses
           GET  /licenses/stats           (静态路径，必须在 /{id} 之前)
           GET  /licenses/{id}
           PUT  /licenses/{id}
  状态机  ：POST /licenses/{id}/suspend
           POST /licenses/{id}/resume
           POST /licenses/{id}/revoke
  续费    ：POST /licenses/{id}/renewal

注意：/stats 必须注册在 /{id} 之前，否则 FastAPI 会把 "stats" 解析为 id。
"""

import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .schemas import (
    LicenseCreateReq,
    LicenseListResp,
    LicenseRenewalReq,
    LicenseResp,
    LicenseStatsResp,
    LicenseUpdateReq,
)
from .services import LicenseService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造许可证管理路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-license-core",
        tags=["ddw-license-core"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-license-core", "version": "1.0.0", "status": "ok"}

    # -----------------------------------------------------------------------
    # 许可证 CRUD —— 静态路径必须先于 {id}
    # -----------------------------------------------------------------------

    @router.post("/licenses", response_model=LicenseResp, status_code=201)
    async def create_license(data: LicenseCreateReq) -> LicenseResp:
        """新建许可证（自动 license_no，状态默认 active）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = LicenseService(db)
            try:
                result = await svc.create(data)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            return LicenseResp(**result)

    @router.get("/licenses", response_model=LicenseListResp)
    async def list_licenses(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页条数"),
        company_id: Optional[int] = Query(None, description="按关联企业 ID 筛选"),
        license_type: Optional[str] = Query(
            None, description="按类型筛选（trial/formal/renewal）"
        ),
        status: Optional[str] = Query(
            None, description="按状态筛选（active/expired/suspended/revoked/renewed）"
        ),
        valid_to_before: Optional[date] = Query(None, description="valid_to <= 该值"),  # noqa: B008
        valid_to_after: Optional[date] = Query(None, description="valid_to >= 该值"),  # noqa: B008
    ) -> LicenseListResp:
        """许可证列表（分页 + 多维筛选；查询前自动标记过期）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = LicenseService(db)
            return await svc.list(
                page=page,
                page_size=page_size,
                company_id=company_id,
                license_type=license_type,
                status=status,
                valid_to_before=valid_to_before,
                valid_to_after=valid_to_after,
            )

    # -----------------------------------------------------------------------
    # 统计（必须注册在 /licenses/{id} 之前）
    # -----------------------------------------------------------------------

    @router.get("/licenses/stats", response_model=LicenseStatsResp)
    async def license_stats() -> LicenseStatsResp:
        """许可证统计概览（read 前自动标记过期）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = LicenseService(db)
            return await svc.stats()

    # -----------------------------------------------------------------------
    # 详情 / 更新
    # -----------------------------------------------------------------------

    @router.get("/licenses/{license_id}", response_model=LicenseResp)
    async def get_license(license_id: int) -> LicenseResp:
        """许可证详情（read 前自动标记过期）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = LicenseService(db)
            result = await svc.get(license_id)
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"license {license_id} not found",
                )
            return LicenseResp(**result)

    @router.put("/licenses/{license_id}", response_model=LicenseResp)
    async def update_license(
        license_id: int, data: LicenseUpdateReq
    ) -> LicenseResp:
        """更新许可证（仅 active / suspended 状态可改）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = LicenseService(db)
            try:
                result = await svc.update(license_id, data)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"license {license_id} not found",
                )
            return LicenseResp(**result)

    # -----------------------------------------------------------------------
    # 状态机迁移
    # -----------------------------------------------------------------------

    @router.post("/licenses/{license_id}/suspend", response_model=LicenseResp)
    async def suspend_license(license_id: int) -> LicenseResp:
        """暂停许可证（active -> suspended）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = LicenseService(db)
            try:
                result = await svc.suspend(license_id)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"license {license_id} not found",
                )
            return LicenseResp(**result)

    @router.post("/licenses/{license_id}/resume", response_model=LicenseResp)
    async def resume_license(license_id: int) -> LicenseResp:
        """恢复许可证（suspended -> active）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = LicenseService(db)
            try:
                result = await svc.resume(license_id)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"license {license_id} not found",
                )
            return LicenseResp(**result)

    @router.post("/licenses/{license_id}/revoke", response_model=LicenseResp)
    async def revoke_license(license_id: int) -> LicenseResp:
        """吊销许可证（active / suspended / expired -> revoked）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = LicenseService(db)
            try:
                result = await svc.revoke(license_id)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"license {license_id} not found",
                )
            return LicenseResp(**result)

    # -----------------------------------------------------------------------
    # 续费
    # -----------------------------------------------------------------------

    @router.post("/licenses/{license_id}/renewal", response_model=LicenseResp, status_code=201)
    async def renew_license(
        license_id: int, data: LicenseRenewalReq
    ) -> LicenseResp:
        """为许可证续费（创建新许可证，旧许可证变 renewed）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = LicenseService(db)
            try:
                result = await svc.renewal(license_id, data)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"license {license_id} not found",
                )
            return LicenseResp(**result)

    return router


__all__ = ["build_router"]
