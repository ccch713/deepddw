from __future__ import annotations

"""DDW 发票管理插件 Pydantic schemas。

包含：
- InvoiceCreateReq：新建开票申请（status=requested）
- InvoiceUpdateReq：更新发票（仅 requested 状态可改）
- InvoiceUploadReq：上传发票文件请求（status: requested → issued, issued_at=今天）
- InvoiceVoidReq：作废发票请求（issued → voided, void_reason 入参）
- InvoiceResp / InvoiceListResp / InvoiceStatsResp：响应
- InvoiceRequestByCustomerReq：客户提交开票申请（Task 2，简化版自动填充抬头）
- InvoiceDownloadResp：发票下载响应（Task 2）
- InvoiceBatchUploadReq / Item：管理员批量上传（Task 2）
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 创建
# ---------------------------------------------------------------------------


class InvoiceCreateReq(BaseModel):
    """新建开票申请请求。

    - 初始 status=requested；issued_at / invoice_no / invoice_url 为空
    - 价税合计 total_amount = amount + tax_amount（服务端在 create 时强制校验）
    """

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")

    company_id: Optional[int] = Field(None, description="关联客户企业 ID（crm_companies.id）")
    order_id: Optional[int] = Field(None, description="关联订单 ID（crm_orders.id）")

    invoice_type: str = Field(
        ..., description="发票类型：special（专票）/ normal（普票）"
    )
    amount: Decimal = Field(..., ge=0, description="金额（不含税，>=0）")
    tax_amount: Decimal = Field(..., ge=0, description="税额（>=0）")
    total_amount: Decimal = Field(..., ge=0, description="价税合计（>=0，必须等于 amount+tax_amount）")

    invoice_title: str = Field(..., min_length=1, max_length=200, description="发票抬头")
    tax_id: str = Field(..., min_length=1, max_length=20, description="税号")

    notes: Optional[str] = Field(None, description="备注")
    created_by: Optional[int] = Field(None, description="创建人 ID")


# ---------------------------------------------------------------------------
# 客户侧开票申请（Task 2：自动从企业主体填充抬头和税号）
# ---------------------------------------------------------------------------


class InvoiceRequestByCustomerReq(BaseModel):
    """客户提交开票申请请求（简化版，从企业主体自动填充）。

    客户只需选择关联的订单/合同，系统自动从企业主体填充抬头和税号。
    """

    company_id: int = Field(..., description="关联客户企业 ID（用于自动读取抬头/税号）")
    order_id: Optional[int] = Field(None, description="关联订单 ID")
    invoice_type: str = Field("normal", description="发票类型：special/normal")
    amount: Decimal = Field(..., ge=0, description="金额（不含税）")
    tax_amount: Decimal = Field(..., ge=0, description="税额")
    total_amount: Decimal = Field(..., ge=0, description="价税合计")
    notes: Optional[str] = Field(None, description="特殊要求（如邮寄地址）")
    created_by: Optional[int] = Field(None, description="创建人 ID")


# ---------------------------------------------------------------------------
# 发票下载响应（Task 2）
# ---------------------------------------------------------------------------


class InvoiceDownloadResp(BaseModel):
    """发票下载响应（MVP 阶段直接返回 URL，不做签名链接）。"""

    invoice_id: int
    invoice_no: Optional[str] = None
    invoice_url: str
    file_type: str  # pdf / ofd / xml
    file_size_bytes: Optional[int] = None
    download_url: str  # MVP 阶段同 invoice_url；后续可扩展为签名临时链接
    download_count: int = 0
    last_downloaded_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# 批量上传（Task 2）
# ---------------------------------------------------------------------------


class InvoiceBatchUploadItem(BaseModel):
    """批量上传条目：一个 invoice_id + 一个发票文件 URL/编号。"""

    invoice_id: int = Field(..., description="开票申请 ID（crm_invoices.id）")
    invoice_url: str = Field(..., min_length=1, max_length=500, description="发票文件 URL")
    invoice_no: str = Field(..., min_length=1, max_length=50, description="发票号")
    invoice_code: Optional[str] = Field(None, max_length=50, description="发票代码")
    invoice_check_code: Optional[str] = Field(None, max_length=50, description="校验码")
    file_type: Optional[str] = Field("pdf", description="文件类型：pdf/ofd/xml")
    file_size_bytes: Optional[int] = Field(None, ge=0, description="文件大小（字节）")
    issued_at: Optional[date] = Field(None, description="开票日期（不传默认今天）")


class InvoiceBatchUploadReq(BaseModel):
    """管理员批量上传发票文件请求。"""

    items: List[InvoiceBatchUploadItem] = Field(..., min_length=1, description="批量上传条目列表")
    notify: bool = Field(False, description="完成后是否通过 EventBus 发布 invoice.issued 事件")


# ---------------------------------------------------------------------------
# 更新（全字段可选；仅 requested 状态可改）
# ---------------------------------------------------------------------------


class InvoiceUpdateReq(BaseModel):
    """更新发票请求（全字段可选；仅 requested 状态可改）。"""

    invoice_type: Optional[str] = Field(None, description="发票类型：special/normal")
    amount: Optional[Decimal] = Field(None, ge=0)
    tax_amount: Optional[Decimal] = Field(None, ge=0)
    total_amount: Optional[Decimal] = Field(None, ge=0)

    invoice_title: Optional[str] = Field(None, min_length=1, max_length=200)
    tax_id: Optional[str] = Field(None, min_length=1, max_length=20)

    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# 上传发票文件（requested → issued）
# ---------------------------------------------------------------------------


class InvoiceUploadReq(BaseModel):
    """上传发票文件请求（requested → issued）。

    - invoice_url 必填（指向 PDF/图片等文件）
    - invoice_no 必填（纸质/电子发票号）
    - issued_at 不传则默认今天
    - amount/tax_amount/total_amount 可选覆盖（默认沿用 create 时的值）
    """

    invoice_url: str = Field(..., min_length=1, max_length=500, description="发票文件 URL（必填）")
    invoice_no: str = Field(..., min_length=1, max_length=50, description="发票号（必填）")
    issued_at: Optional[date] = Field(None, description="开票日期（不传默认今天）")
    amount: Optional[Decimal] = Field(None, ge=0, description="实际开票金额（不含税）")
    tax_amount: Optional[Decimal] = Field(None, ge=0, description="实际开票税额")
    total_amount: Optional[Decimal] = Field(None, ge=0, description="实际价税合计")
    invoice_code: Optional[str] = Field(None, max_length=50, description="发票代码")
    invoice_check_code: Optional[str] = Field(None, max_length=50, description="校验码")
    file_type: Optional[str] = Field("pdf", max_length=10, description="文件类型：pdf/ofd/xml")
    file_size_bytes: Optional[int] = Field(None, ge=0, description="文件大小（字节）")


# ---------------------------------------------------------------------------
# 作废（issued → voided）
# ---------------------------------------------------------------------------


class InvoiceVoidReq(BaseModel):
    """作废发票请求（issued → voided）。"""

    void_reason: str = Field(
        ..., min_length=1, max_length=500, description="作废原因（必填）"
    )


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------


class InvoiceResp(BaseModel):
    """发票响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int

    company_id: Optional[int] = None
    order_id: Optional[int] = None

    invoice_no: Optional[str] = None
    invoice_type: str

    amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal

    invoice_title: str
    tax_id: str

    invoice_url: Optional[str] = None
    issued_at: Optional[date] = None

    status: str
    notes: Optional[str] = None

    # Task 1 新增字段（响应侧可选，默认 None）
    notified_at: Optional[datetime] = None
    notification_method: Optional[str] = None
    download_count: int = 0
    last_downloaded_at: Optional[datetime] = None
    last_downloaded_by: Optional[int] = None
    invoice_code: Optional[str] = None
    invoice_check_code: Optional[str] = None
    file_type: Optional[str] = None
    file_size_bytes: Optional[int] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[int] = None


class InvoiceListResp(BaseModel):
    """发票分页列表响应。"""

    total: int
    page: int
    page_size: int
    items: List[InvoiceResp]


class InvoiceStatsResp(BaseModel):
    """发票统计概览。

    - 各状态计数（total/requested/issued/voided）
    - 金额汇总（total_amount：所有价税合计之和；tax_amount：所有税额之和）
    - by_invoice_type：按发票类型分组的发票数
    - download_total: 所有发票下载次数之和（Task 1）
    - total_downloaded_files: 已开票且至少有 1 次下载的发票数（Task 1）
    """

    total: int
    requested: int
    issued: int
    voided: int

    total_amount: Decimal = Field(Decimal("0"), description="所有价税合计之和")
    tax_amount: Decimal = Field(Decimal("0"), description="所有税额之和")

    by_invoice_type: Dict[str, int] = Field(
        default_factory=dict, description="按发票类型分组（special/normal）"
    )

    # Task 1 新增下载维度
    download_total: int = Field(0, description="所有发票下载次数之和")
    total_downloaded_files: int = Field(0, description="已开票且至少下载 1 次的发票数")


__all__ = [
    "InvoiceCreateReq",
    "InvoiceRequestByCustomerReq",
    "InvoiceDownloadResp",
    "InvoiceBatchUploadItem",
    "InvoiceBatchUploadReq",
    "InvoiceListResp",
    "InvoiceResp",
    "InvoiceStatsResp",
    "InvoiceUpdateReq",
    "InvoiceUploadReq",
    "InvoiceVoidReq",
]
