from __future__ import annotations

from typing import Optional

"""DDW 电子签章适配器插件 API 路由。

API 端点（8 个）：
  健康检查：GET  /health
  签署请求：POST /signature-requests                            新建（不真正调第三方）
           GET  /signature-requests                            列表（分页 + 筛选）
           GET  /signature-requests/stats                      统计（静态路径优先）
           GET  /signature-requests/{id}                       详情
           PUT  /signature-requests/{id}                       更新（仅 pending）
  异步回调：POST /signature-requests/{id}/callback             第三方回调
  人工上传：POST /signature-requests/{id}/manual-upload        人工上传签后文件

注意：/signature-requests/stats 必须注册在 /signature-requests/{id} 之前，
否则 FastAPI 会把 "stats" 解析为 id。
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .schemas import (
    CallbackReq,
    ManualUploadReq,
    SignatureRequestCreateReq,
    SignatureRequestListResp,
    SignatureRequestResp,
    SignatureRequestStatsResp,
    SignatureRequestUpdateReq,
)
from .services import SignatureRequestService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造电子签章适配器路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-signature-adapter",
        tags=["ddw-signature-adapter"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-signature-adapter", "version": "1.0.0", "status": "ok"}

    # -----------------------------------------------------------------------
    # 签署请求 CRUD —— 静态路径必须先于 {id}
    # -----------------------------------------------------------------------

    @router.post(
        "/signature-requests",
        response_model=SignatureRequestResp,
        status_code=201,
    )
    async def create_signature_request(
        data: SignatureRequestCreateReq,
    ) -> SignatureRequestResp:
        """新建签署请求（不真正调用第三方 API，仅落库，状态默认 pending）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = SignatureRequestService(db)
            try:
                result = await svc.create(data)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            return SignatureRequestResp(**result)

    @router.get(
        "/signature-requests",
        response_model=SignatureRequestListResp,
    )
    async def list_signature_requests(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页条数"),
        contract_id: Optional[int] = Query(None, description="按关联合同 ID 筛选"),
        provider: Optional[str] = Query(
            None, description="按服务商筛选（tencent/dianxiaoyu/esign/manual）"
        ),
        status: Optional[str] = Query(
            None, description="按状态筛选（pending/signing/signed/rejected/expired）"
        ),
    ) -> SignatureRequestListResp:
        """签署请求列表（分页 + 多维筛选）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = SignatureRequestService(db)
            return await svc.list(
                page=page,
                page_size=page_size,
                contract_id=contract_id,
                provider=provider,
                status=status,
            )

    # -----------------------------------------------------------------------
    # 统计（必须注册在 /signature-requests/{id} 之前）
    # -----------------------------------------------------------------------

    @router.get(
        "/signature-requests/stats",
        response_model=SignatureRequestStatsResp,
    )
    async def signature_request_stats() -> SignatureRequestStatsResp:
        """签署请求统计概览。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = SignatureRequestService(db)
            return await svc.stats()

    # -----------------------------------------------------------------------
    # 详情 / 更新
    # -----------------------------------------------------------------------

    @router.get(
        "/signature-requests/{request_id}",
        response_model=SignatureRequestResp,
    )
    async def get_signature_request(request_id: int) -> SignatureRequestResp:
        """签署请求详情。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = SignatureRequestService(db)
            result = await svc.get(request_id)
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"signature request {request_id} not found",
                )
            return SignatureRequestResp(**result)

    @router.put(
        "/signature-requests/{request_id}",
        response_model=SignatureRequestResp,
    )
    async def update_signature_request(
        request_id: int,
        data: SignatureRequestUpdateReq,
    ) -> SignatureRequestResp:
        """更新签署请求（仅 pending 状态可改）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = SignatureRequestService(db)
            try:
                result = await svc.update(request_id, data)
            except LookupError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            return SignatureRequestResp(**result)

    # -----------------------------------------------------------------------
    # 异步回调（第三方 -> 本系统）
    # -----------------------------------------------------------------------

    @router.post(
        "/signature-requests/{request_id}/callback",
        response_model=SignatureRequestResp,
    )
    async def callback_signature_request(
        request_id: int,
        payload: CallbackReq,
    ) -> SignatureRequestResp:
        """第三方异步回调：更新 status / signed_at / signed_document_url。

        目标 status 必须在白名单内（signed / rejected / expired）。
        已处于目标状态时按幂等处理。
        """
        async with session_scope() as db, bypass_tenant_filter():
            svc = SignatureRequestService(db)
            try:
                result = await svc.callback(request_id, payload)
            except LookupError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            return SignatureRequestResp(**result)

    # -----------------------------------------------------------------------
    # 人工上传签后文件
    # -----------------------------------------------------------------------

    @router.post(
        "/signature-requests/{request_id}/manual-upload",
        response_model=SignatureRequestResp,
    )
    async def manual_upload_signed_document(
        request_id: int,
        payload: ManualUploadReq,
    ) -> SignatureRequestResp:
        """人工上传签后文件：status -> signed，signed_document_url 必填。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = SignatureRequestService(db)
            try:
                result = await svc.manual_upload(request_id, payload)
            except LookupError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            return SignatureRequestResp(**result)

    return router


__all__ = ["build_router"]
