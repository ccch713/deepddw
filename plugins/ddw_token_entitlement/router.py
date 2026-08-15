from __future__ import annotations

"""DDW Token 额度管理插件 API 路由。

API 端点（8 个）：
  健康检查：GET  /health
  额度分配：POST /entitlements
           GET  /entitlements
           GET  /entitlements/stats            (静态路径，必须在 /{id} 之前)
           GET  /entitlements/{id}
           PUT  /entitlements/{id}
           DELETE /entitlements/{id}            (硬删除)
           POST /entitlements/{id}/consume      (消耗 tokens)

注意：/stats 必须注册在 /{id} 之前，否则 FastAPI 会把 "stats" 解析为 id。
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .schemas import (
    TokenConsumeReq,
    TokenConsumeResp,
    TokenEntitlementCreateReq,
    TokenEntitlementListResp,
    TokenEntitlementResp,
    TokenEntitlementStatsResp,
    TokenEntitlementUpdateReq,
)
from .services import TokenEntitlementService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造 Token 额度管理路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-token-entitlement",
        tags=["ddw-token-entitlement"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict:
        return {
            "plugin": "ddw-token-entitlement",
            "version": "1.0.0",
            "status": "ok",
        }

    # -----------------------------------------------------------------------
    # 额度分配 CRUD —— 静态路径必须先于 {id}
    # -----------------------------------------------------------------------

    @router.post("/entitlements", response_model=TokenEntitlementResp, status_code=201)
    async def create_entitlement(
        data: TokenEntitlementCreateReq,
    ) -> TokenEntitlementResp:
        """新建额度分配。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = TokenEntitlementService(db)
            try:
                result = await svc.create(data)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            return TokenEntitlementResp(**result)

    @router.get("/entitlements", response_model=TokenEntitlementListResp)
    async def list_entitlements(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页条数"),
        company_id: Optional[int] = Query(None, description="按关联企业 ID 筛选"),
        instance_id: Optional[int] = Query(None, description="按关联实例 ID 筛选"),
        entitlement_type: Optional[str] = Query(
            None, description="按额度类型筛选（platform/custom-key/local-llm）"
        ),
    ) -> TokenEntitlementListResp:
        """额度分配列表（分页 + 多维筛选）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = TokenEntitlementService(db)
            return await svc.list(
                page=page,
                page_size=page_size,
                company_id=company_id,
                instance_id=instance_id,
                entitlement_type=entitlement_type,
            )

    # -----------------------------------------------------------------------
    # 统计（必须注册在 /entitlements/{id} 之前）
    # -----------------------------------------------------------------------

    @router.get("/entitlements/stats", response_model=TokenEntitlementStatsResp)
    async def entitlement_stats() -> TokenEntitlementStatsResp:
        """额度分配统计概览。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = TokenEntitlementService(db)
            return await svc.stats()

    # -----------------------------------------------------------------------
    # 详情 / 更新 / 删除
    # -----------------------------------------------------------------------

    @router.get("/entitlements/{ent_id}", response_model=TokenEntitlementResp)
    async def get_entitlement(ent_id: int) -> TokenEntitlementResp:
        """额度分配详情。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = TokenEntitlementService(db)
            result = await svc.get(ent_id)
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"token entitlement {ent_id} not found",
                )
            return TokenEntitlementResp(**result)

    @router.put("/entitlements/{ent_id}", response_model=TokenEntitlementResp)
    async def update_entitlement(
        ent_id: int, data: TokenEntitlementUpdateReq
    ) -> TokenEntitlementResp:
        """更新额度分配（不能改 used_tokens / tenant_id）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = TokenEntitlementService(db)
            try:
                result = await svc.update(ent_id, data)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"token entitlement {ent_id} not found",
                )
            return TokenEntitlementResp(**result)

    @router.delete("/entitlements/{ent_id}", response_model=dict)
    async def delete_entitlement(ent_id: int) -> dict:
        """删除额度分配（硬删除）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = TokenEntitlementService(db)
            ok = await svc.delete(ent_id)
            if not ok:
                raise HTTPException(
                    status_code=404,
                    detail=f"token entitlement {ent_id} not found",
                )
            return {"id": ent_id, "deleted": True}

    # -----------------------------------------------------------------------
    # 消耗
    # -----------------------------------------------------------------------

    @router.post(
        "/entitlements/{ent_id}/consume",
        response_model=TokenConsumeResp,
    )
    async def consume_tokens(
        ent_id: int, data: TokenConsumeReq
    ) -> TokenConsumeResp:
        """消耗 tokens。

        - 拒绝超量（overage_allowed=False）时返回 400
        - 允许超量时正常累加 used_tokens，响应中 overage 为负数
        """
        async with session_scope() as db, bypass_tenant_filter():
            svc = TokenEntitlementService(db)
            try:
                result = await svc.consume(ent_id, data)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"token entitlement {ent_id} not found",
                )
            return TokenConsumeResp(**result)

    return router


__all__ = ["build_router"]
