from __future__ import annotations

from typing import Optional

"""DDW 实例绑定插件 API 路由。

API 端点（8 个）：
  健康检查：GET  /health
  实例    ：POST /instances
            GET  /instances
            GET  /instances/stats           (静态路径，必须在 /{id} 之前)
            GET  /instances/{id}
            PUT  /instances/{id}
  软删除  ：DELETE /instances/{id}
  心跳    ：POST /instances/{id}/heartbeat

注意：/stats 必须注册在 /{id} 之前，否则 FastAPI 会把 "stats" 解析为 id。
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .schemas import (
    InstanceCreateReq,
    InstanceHeartbeatReq,
    InstanceListResp,
    InstanceResp,
    InstanceStatsResp,
    InstanceUpdateReq,
)
from .services import InstanceService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造实例绑定路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-instance-binding",
        tags=["ddw-instance-binding"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-instance-binding", "version": "1.0.0", "status": "ok"}

    # -----------------------------------------------------------------------
    # 实例 CRUD —— 静态路径必须先于 /{id}
    # -----------------------------------------------------------------------

    @router.post("/instances", response_model=InstanceResp, status_code=201)
    async def create_instance(data: InstanceCreateReq) -> InstanceResp:
        """绑定实例。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = InstanceService(db)
            try:
                result = await svc.create(data)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            return InstanceResp(**result)

    @router.get("/instances", response_model=InstanceListResp)
    async def list_instances(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页条数"),
        company_id: Optional[int] = Query(None, description="按关联企业 ID 筛选"),
        license_id: Optional[int] = Query(None, description="按关联许可证 ID 筛选"),
        instance_type: Optional[str] = Query(
            None, description="按实例类型筛选（saas/on-premise）"
        ),
        environment: Optional[str] = Query(
            None, description="按环境筛选（production/staging/test）"
        ),
        status: Optional[str] = Query(
            None, description="按状态筛选（active/inactive/suspended）"
        ),
    ) -> InstanceListResp:
        """实例列表（分页 + 多维筛选）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = InstanceService(db)
            return await svc.list(
                page=page,
                page_size=page_size,
                company_id=company_id,
                license_id=license_id,
                instance_type=instance_type,
                environment=environment,
                status=status,
            )

    # -----------------------------------------------------------------------
    # 统计（必须注册在 /instances/{id} 之前）
    # -----------------------------------------------------------------------

    @router.get("/instances/stats", response_model=InstanceStatsResp)
    async def instance_stats() -> InstanceStatsResp:
        """实例统计概览。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = InstanceService(db)
            return await svc.stats()

    # -----------------------------------------------------------------------
    # 详情 / 更新
    # -----------------------------------------------------------------------

    @router.get("/instances/{instance_id}", response_model=InstanceResp)
    async def get_instance(instance_id: int) -> InstanceResp:
        """实例详情。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = InstanceService(db)
            result = await svc.get(instance_id)
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"instance {instance_id} not found",
                )
            return InstanceResp(**result)

    @router.put("/instances/{instance_id}", response_model=InstanceResp)
    async def update_instance(
        instance_id: int, data: InstanceUpdateReq
    ) -> InstanceResp:
        """更新实例（不可改 instance_id / instance_type / company_id / license_id）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = InstanceService(db)
            try:
                result = await svc.update(instance_id, data)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"instance {instance_id} not found",
                )
            return InstanceResp(**result)

    # -----------------------------------------------------------------------
    # 软删除
    # -----------------------------------------------------------------------

    @router.delete("/instances/{instance_id}", response_model=InstanceResp)
    async def delete_instance(instance_id: int) -> InstanceResp:
        """软删除：status -> suspended（保留审计链）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = InstanceService(db)
            result = await svc.suspend(instance_id)
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"instance {instance_id} not found",
                )
            return InstanceResp(**result)

    # -----------------------------------------------------------------------
    # 心跳
    # -----------------------------------------------------------------------

    @router.post("/instances/{instance_id}/heartbeat", response_model=InstanceResp)
    async def heartbeat_instance(
        instance_id: int, data: InstanceHeartbeatReq | None = None
    ) -> InstanceResp:
        """心跳上报：更新 last_heartbeat = now()，可选同时更新 status。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = InstanceService(db)
            try:
                result = await svc.heartbeat(instance_id, data)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"instance {instance_id} not found",
                )
            return InstanceResp(**result)

    return router


__all__ = ["build_router"]
