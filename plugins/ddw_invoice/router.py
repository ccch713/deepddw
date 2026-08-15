from __future__ import annotations

"""DDW 发票管理插件 API 路由。

API 端点（12 个）：
  健康检查：GET  /health
  发票管理：
    POST /invoices                       # 新建开票申请（管理员）
    GET  /invoices                       # 列表（分页 + 多维筛选）
    GET  /invoices/stats                 # 统计（必须在 /{id} 之前）
    GET  /invoices/{id}                  # 详情
    PUT  /invoices/{id}                  # 更新（仅 requested 状态）
    POST /invoices/{id}/upload           # 上传发票（requested → issued）
    POST /invoices/{id}/void             # 作废（issued → voided）
  客户侧（MVP）：
    POST /invoices/request               # 客户提交开票申请（自动填充抬头）
    GET  /invoices/my                    # 客户查自己的发票列表
    GET  /invoices/{id}/download         # 客户下载发票（仅 issued，递增计数）
  管理员批量：
    POST /invoices/batch-upload          # 批量上传多个发票文件

注意：/stats 必须注册在 /{id} 之前，否则 FastAPI 会把 "stats" 解析为 id。
"""

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .schemas import (
    InvoiceBatchUploadReq,
    InvoiceCreateReq,
    InvoiceDownloadResp,
    InvoiceListResp,
    InvoiceRequestByCustomerReq,
    InvoiceStatsResp,
    InvoiceUpdateReq,
    InvoiceUploadReq,
    InvoiceVoidReq,
)
from .services import InvoiceService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造发票管理路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-invoice",
        tags=["ddw-invoice"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-invoice", "version": "1.0.0", "status": "ok"}

    # -----------------------------------------------------------------------
    # 客户侧：开票申请 + 我的发票 + 下载（Task 3）
    # 静态路径 /request, /my, /batch-upload 必须先于 /{invoice_id}
    # -----------------------------------------------------------------------

    @router.post("/invoices/request", response_model=dict, status_code=201)
    async def request_invoice(data: InvoiceRequestByCustomerReq) -> dict:
        """客户提交开票申请（自动从企业主体填充抬头和税号）。

        - 从 company_id 自动读取 invoice_title / tax_id
        - 创建 Invoice 记录，status=requested
        - 发布 EventBus 事件 invoice.requested
        """
        async with session_scope() as db, bypass_tenant_filter():
            svc = InvoiceService(db)
            try:
                return await svc.request_by_customer(data)
            except ValueError as e:
                msg = str(e)
                # 企业不存在 → 404；其他校验失败 → 400
                if "不存在" in msg:
                    raise HTTPException(status_code=404, detail=msg)
                raise HTTPException(status_code=400, detail=msg)

    @router.get("/invoices/my", response_model=InvoiceListResp)
    async def list_my_invoices(
        company_id: int = Query(..., description="企业 ID（必填，仅返回本企业的发票）"),
        status: Optional[str] = Query(
            None, description="按状态筛选（requested/issued/voided）"
        ),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    ) -> InvoiceListResp:
        """客户查看自己的发票列表。

        - 强制 company_id 精确匹配（防止越权查看其他企业）
        - 按 created_at 降序（实际按 Invoice.id.desc() 实现，时间一致）
        """
        async with session_scope() as db, bypass_tenant_filter():
            svc = InvoiceService(db)
            return await svc.list_by_company(
                company_id=company_id,
                status=status,
                page=page,
                page_size=page_size,
            )

    @router.post("/invoices/batch-upload", response_model=dict)
    async def batch_upload_invoices(data: InvoiceBatchUploadReq) -> dict:
        """管理员批量上传发票文件并关联到多个开票申请。

        - 支持一次提交多条（items 长度 ≥ 1）
        - 每条状态独立：requested → issued；非法状态会单独失败但不阻断其他条
        - notify=true 时完成后发布 EventBus 事件 invoice.batch_issued
        """
        async with session_scope() as db, bypass_tenant_filter():
            svc = InvoiceService(db)
            return await svc.batch_upload(data)

    # -----------------------------------------------------------------------
    # 发票 CRUD —— 静态路径必须先于 {id}
    # -----------------------------------------------------------------------

    @router.post("/invoices", response_model=dict, status_code=201)
    async def create_invoice(data: InvoiceCreateReq) -> dict:
        """新建开票申请（status=requested，管理员版）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = InvoiceService(db)
            try:
                return await svc.create(data)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

    @router.get("/invoices", response_model=InvoiceListResp)
    async def list_invoices(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页条数"),
        company_id: Optional[int] = Query(None, description="按关联企业 ID 筛选"),
        order_id: Optional[int] = Query(None, description="按关联订单 ID 筛选"),
        invoice_type: Optional[str] = Query(
            None, description="按发票类型筛选（special/normal）"
        ),
        status: Optional[str] = Query(
            None, description="按状态筛选（requested/issued/voided）"
        ),
        issued_at_from: Optional[date] = Query(
            None, description="开票日期起（含）"
        ),
        issued_at_to: Optional[date] = Query(
            None, description="开票日期止（含）"
        ),
    ) -> InvoiceListResp:
        """发票列表（分页 + 多维筛选）。

        支持的筛选维度：企业、订单、发票类型、状态、开票日期区间。
        """
        async with session_scope() as db, bypass_tenant_filter():
            svc = InvoiceService(db)
            return await svc.list(
                page=page,
                page_size=page_size,
                company_id=company_id,
                order_id=order_id,
                invoice_type=invoice_type,
                status=status,
                issued_at_from=issued_at_from,
                issued_at_to=issued_at_to,
            )

    # -----------------------------------------------------------------------
    # 专用端点：统计（必须在 /{id} 之前）
    # -----------------------------------------------------------------------

    @router.get("/invoices/stats", response_model=InvoiceStatsResp)
    async def invoice_stats() -> InvoiceStatsResp:
        """发票统计概览。

        - 各状态计数（total/requested/issued/voided）
        - 金额汇总（total_amount 价税合计之和；tax_amount 税额之和）
        - by_invoice_type：按发票类型分组
        - download_total / total_downloaded_files：下载维度（Task 1）
        """
        async with session_scope() as db, bypass_tenant_filter():
            svc = InvoiceService(db)
            return await svc.stats()

    # -----------------------------------------------------------------------
    # 详情 / 更新
    # -----------------------------------------------------------------------

    @router.get("/invoices/{invoice_id}", response_model=dict)
    async def get_invoice(invoice_id: int) -> dict:
        """发票详情。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = InvoiceService(db)
            result = await svc.get(invoice_id)
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"invoice {invoice_id} not found",
                )
            return result

    @router.put("/invoices/{invoice_id}", response_model=dict)
    async def update_invoice(
        invoice_id: int, data: InvoiceUpdateReq
    ) -> dict:
        """更新发票（仅 requested 状态可改）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = InvoiceService(db)
            try:
                result = await svc.update(invoice_id, data)
            except ValueError as e:
                raise HTTPException(status_code=409, detail=str(e))
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"invoice {invoice_id} not found",
                )
            return result

    # -----------------------------------------------------------------------
    # 客户侧下载（Task 3.3：GET /{id}/download）
    # -----------------------------------------------------------------------

    @router.get("/invoices/{invoice_id}/download", response_model=InvoiceDownloadResp)
    async def download_invoice(
        invoice_id: int,
        user_id: Optional[int] = Query(
            None, description="下载人 ID（MVP 阶段可不传，生产从 JWT 取）"
        ),
    ) -> InvoiceDownloadResp:
        """客户下载发票文件。

        - 仅允许 status=issued 的发票
        - 增加 download_count，更新 last_downloaded_at / last_downloaded_by
        - 返回 invoice_url（MVP 阶段直接返回 URL，不做签名链接）
        """
        async with session_scope() as db, bypass_tenant_filter():
            svc = InvoiceService(db)
            try:
                return await svc.record_download(invoice_id, user_id=user_id)
            except ValueError as e:
                msg = str(e)
                if "不存在" in msg:
                    raise HTTPException(status_code=404, detail=msg)
                raise HTTPException(status_code=400, detail=msg)

    # -----------------------------------------------------------------------
    # 上传发票（requested → issued）
    # -----------------------------------------------------------------------

    @router.post("/invoices/{invoice_id}/upload", response_model=dict)
    async def upload_invoice(
        invoice_id: int, data: InvoiceUploadReq
    ) -> dict:
        """上传发票文件（requested → issued）。

        - invoice_url / invoice_no 必填
        - issued_at 不传则默认今天
        """
        async with session_scope() as db, bypass_tenant_filter():
            svc = InvoiceService(db)
            try:
                result = await svc.upload(invoice_id, data)
            except ValueError as e:
                raise HTTPException(status_code=409, detail=str(e))
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"invoice {invoice_id} not found",
                )
            return result

    # -----------------------------------------------------------------------
    # 作废（issued → voided）
    # -----------------------------------------------------------------------

    @router.post("/invoices/{invoice_id}/void", response_model=dict)
    async def void_invoice(
        invoice_id: int, data: InvoiceVoidReq
    ) -> dict:
        """作废发票（issued → voided，void_reason 入参）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = InvoiceService(db)
            try:
                result = await svc.void(invoice_id, data)
            except ValueError as e:
                raise HTTPException(status_code=409, detail=str(e))
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"invoice {invoice_id} not found",
                )
            return result

    return router


__all__ = ["build_router"]
