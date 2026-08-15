from __future__ import annotations

"""DDW 合同中心插件 API 路由。

API 端点（13 个）：
  健康检查：GET  /health
  合同 CRUD ：POST /contracts, GET /contracts, GET /contracts/stats
            GET /contracts/{id}, PUT /contracts/{id}
  状态机  ：POST /contracts/{id}/submit-approval
            POST /contracts/{id}/approve
            POST /contracts/{id}/reject
            POST /contracts/{id}/sign
            POST /contracts/{id}/activate
            POST /contracts/{id}/terminate
            POST /contracts/{id}/complete

注意：stats 必须注册在 {id} 之前，否则 FastAPI 会把 "stats" 解析为 id。
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .schemas import (
    ContractCreateReq,
    ContractListResp,
    ContractStatsResp,
    ContractUpdateReq,
    RejectReq,
    TerminateReq,
)
from .services import ContractService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造合同中心管理路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-contract-core",
        tags=["ddw-contract-core"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-contract-core", "version": "1.0.0", "status": "ok"}

    # -----------------------------------------------------------------------
    # 合同 CRUD —— 静态路径必须先于 {id}
    # -----------------------------------------------------------------------

    @router.post("/contracts", response_model=dict, status_code=201)
    async def create_contract(data: ContractCreateReq) -> dict:
        """新建合同（状态默认 draft，自动生成单号 CT-YYYYMMDD-NNN）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ContractService(db)
                try:
                    return await svc.create(data)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))

    @router.get("/contracts", response_model=ContractListResp)
    async def list_contracts(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页条数"),
        search: Optional[str] = Query(
            None, description="模糊搜索（单号 / 标题）"
        ),
        status: Optional[str] = Query(
            None,
            description=(
                "状态筛选（draft/pending_approval/approved/signed/active/"
                "completed/terminated/rejected）"
            ),
        ),
        contract_type: Optional[str] = Query(
            None, description="合同类型筛选（standard/framework/supplementary）"
        ),
        company_id: Optional[int] = Query(None, description="按关联企业 ID 筛选"),
    ) -> ContractListResp:
        """合同列表（分页 + 筛选 + 搜索）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ContractService(db)
                return await svc.list(
                    page=page,
                    page_size=page_size,
                    search=search,
                    status=status,
                    contract_type=contract_type,
                    company_id=company_id,
                )

    # -----------------------------------------------------------------------
    # 统计（必须注册在 /contracts/{id} 之前）
    # -----------------------------------------------------------------------

    @router.get("/contracts/stats", response_model=ContractStatsResp)
    async def contract_stats() -> ContractStatsResp:
        """合同统计概览。

        - 各状态计数
        - 按 contract_type 分组
        - 总金额 / 激活合同金额 / 已完结合同金额
        """
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ContractService(db)
                return await svc.stats()

    # -----------------------------------------------------------------------
    # 详情 / 更新
    # -----------------------------------------------------------------------

    @router.get("/contracts/{contract_id}", response_model=dict)
    async def get_contract(contract_id: int) -> dict:
        """合同详情。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ContractService(db)
                result = await svc.get(contract_id)
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"contract {contract_id} not found",
                    )
                return result

    @router.put("/contracts/{contract_id}", response_model=dict)
    async def update_contract(
        contract_id: int, data: ContractUpdateReq
    ) -> dict:
        """更新合同（仅 draft / rejected 状态可改）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ContractService(db)
                try:
                    result = await svc.update(contract_id, data)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"contract {contract_id} not found",
                    )
                return result

    # -----------------------------------------------------------------------
    # 状态机迁移
    # -----------------------------------------------------------------------

    @router.post("/contracts/{contract_id}/submit-approval", response_model=dict)
    async def submit_contract_approval(contract_id: int) -> dict:
        """提交审批（draft → pending_approval）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ContractService(db)
                try:
                    result = await svc.submit_approval(contract_id)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"contract {contract_id} not found",
                    )
                return result

    @router.post("/contracts/{contract_id}/approve", response_model=dict)
    async def approve_contract(contract_id: int) -> dict:
        """审批通过（pending_approval → approved）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ContractService(db)
                try:
                    result = await svc.approve(contract_id)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"contract {contract_id} not found",
                    )
                return result

    @router.post("/contracts/{contract_id}/reject", response_model=dict)
    async def reject_contract(contract_id: int, data: RejectReq) -> dict:
        """审批驳回（pending_approval → rejected, reason 必填）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ContractService(db)
                try:
                    result = await svc.reject(contract_id, data)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"contract {contract_id} not found",
                    )
                return result

    @router.post("/contracts/{contract_id}/sign", response_model=dict)
    async def sign_contract(contract_id: int) -> dict:
        """标记已签（approved → signed, signed_at=now）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ContractService(db)
                try:
                    result = await svc.sign(contract_id)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"contract {contract_id} not found",
                    )
                return result

    @router.post("/contracts/{contract_id}/activate", response_model=dict)
    async def activate_contract(contract_id: int) -> dict:
        """激活合同（signed → active）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ContractService(db)
                try:
                    result = await svc.activate(contract_id)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"contract {contract_id} not found",
                    )
                return result

    @router.post("/contracts/{contract_id}/terminate", response_model=dict)
    async def terminate_contract(
        contract_id: int, data: TerminateReq
    ) -> dict:
        """终止合同（signed / active → terminated, reason 必填）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ContractService(db)
                try:
                    result = await svc.terminate(contract_id, data)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"contract {contract_id} not found",
                    )
                return result

    @router.post("/contracts/{contract_id}/complete", response_model=dict)
    async def complete_contract(contract_id: int) -> dict:
        """完成合同（active → completed）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = ContractService(db)
                try:
                    result = await svc.complete(contract_id)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"contract {contract_id} not found",
                    )
                return result

    return router


__all__ = ["build_router"]
