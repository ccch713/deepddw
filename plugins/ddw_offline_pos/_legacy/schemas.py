from __future__ import annotations

"""DDW 实收管理插件 Pydantic schemas。

包含：
- PaymentCreateReq：创建实收请求
- PaymentUpdateReq：更新实收请求（仅 pending 状态可改）
- PaymentResp：实收响应
- PaymentListResp：分页列表
- PaymentStatsResp：统计概览
- PaymentUnmatchedItemResp：未核销列表项（与 PaymentResp 同构，复用）
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 创建 / 更新
# ---------------------------------------------------------------------------


class PaymentCreateReq(BaseModel):
    """新建实收请求。

    - payment_no 由服务端自动生成（PAY-YYYYMMDD-NNN），无需传入
    - status 默认 pending；matched_amount 默认 0
    - payer_name 必填（即便已选 company_id，也需填付款方全名以便银行流水核对）
    """

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")

    company_id: Optional[int] = Field(None, description="关联客户企业 ID（crm_companies.id）")

    payer_name: str = Field(..., min_length=1, max_length=200, description="付款企业全名（必填）")
    bank_reference: Optional[str] = Field(
        None, max_length=100, description="银行流水号"
    )
    bank_account: Optional[str] = Field(
        None, max_length=50, description="收款账户"
    )

    amount: Decimal = Field(..., ge=0, description="收款金额（>=0）")
    payment_date: date = Field(..., description="收款日期")
    payment_method: str = Field(
        ...,
        min_length=1,
        max_length=30,
        description="支付方式：bank/cheque/cash/wechat/alipay",
    )

    notes: Optional[str] = Field(None, description="备注")

    created_by: Optional[int] = Field(None, description="创建人 ID")


class PaymentUpdateReq(BaseModel):
    """更新实收请求（全字段可选；仅 pending 状态可改）。"""

    company_id: Optional[int] = None
    payer_name: Optional[str] = Field(None, min_length=1, max_length=200)
    bank_reference: Optional[str] = Field(None, max_length=100)
    bank_account: Optional[str] = Field(None, max_length=50)

    amount: Optional[Decimal] = Field(None, ge=0)
    payment_date: Optional[date] = None
    payment_method: Optional[str] = Field(None, min_length=1, max_length=30)

    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------


class PaymentResp(BaseModel):
    """实收响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int

    company_id: Optional[int] = None

    payment_no: str
    payer_name: str
    bank_reference: Optional[str] = None
    bank_account: Optional[str] = None

    amount: Decimal
    payment_date: date
    payment_method: str

    notes: Optional[str] = None

    status: str
    matched_amount: Decimal

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[int] = None

    # 派生字段（仅未核销列表填充）
    unmatched_amount: Optional[Decimal] = Field(
        None, description="未核销金额 = amount - matched_amount（仅未核销列表填充）"
    )


class PaymentListResp(BaseModel):
    """实收分页列表响应。"""

    total: int
    page: int
    page_size: int
    items: List[PaymentResp]


class PaymentUnmatchedListResp(BaseModel):
    """未核销实收列表响应（仅 status=pending/partial）。"""

    total: int
    page: int
    page_size: int
    items: List[PaymentResp]


class PaymentStatsResp(BaseModel):
    """实收统计概览。

    - 各状态计数（total/pending/partial/matched/unmatched）
    - 金额汇总（total_amount：所有实收金额之和；matched_amount：已核销金额之和；
      unmatched_amount：未核销金额 = total_amount - matched_amount）
    """

    total: int
    pending: int
    partial: int
    matched: int
    unmatched: int
    total_amount: Decimal = Field(Decimal(0), description="所有实收金额之和")
    matched_amount: Decimal = Field(Decimal(0), description="已核销金额之和（由 P1-5 维护）")
    unmatched_amount: Decimal = Field(Decimal(0), description="未核销金额之和 = total - matched")


__all__ = [
    "PaymentCreateReq",
    "PaymentListResp",
    "PaymentResp",
    "PaymentStatsResp",
    "PaymentUnmatchedListResp",
    "PaymentUpdateReq",
]
