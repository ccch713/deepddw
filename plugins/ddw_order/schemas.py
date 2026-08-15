from __future__ import annotations

"""DDW 订单管理插件 Pydantic schemas。

包含：
- OrderItemReq / OrderItemResp：明细行请求与响应（unit_price / amount 走 Decimal 字符串）
- OrderCreateReq：创建订单（含 items 列表）
- OrderUpdateReq：更新订单（全字段可选，仅 pending 可改）
- OrderCancelReq：取消请求（reason 必填）
- OrderResp：订单响应（含 items）
- OrderListResp：分页列表
- OrderStatsResp：统计概览
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 明细（OrderItem）
# ---------------------------------------------------------------------------


class OrderItemReq(BaseModel):
    """订单明细请求（创建 / 更新时复用）。"""

    product_name: str = Field(..., min_length=1, max_length=200, description="产品/服务名称")
    quantity: int = Field(1, ge=1, description="数量（>=1）")
    unit_price: Optional[Decimal] = Field(None, ge=0, description="单价")
    amount: Optional[Decimal] = Field(
        None, ge=0, description="金额（=quantity × unit_price；不传则服务端计算）"
    )


class OrderItemResp(BaseModel):
    """订单明细响应。"""

    product_name: str
    quantity: int
    unit_price: Optional[Decimal] = None
    amount: Optional[Decimal] = None


# ---------------------------------------------------------------------------
# 创建 / 更新 / 取消
# ---------------------------------------------------------------------------


class OrderCreateReq(BaseModel):
    """新建订单请求（可空 items，items 空则 total_amount = 0）。"""

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")

    company_id: Optional[int] = Field(None, description="关联客户企业 ID")
    contract_id: Optional[int] = Field(None, description="关联合同 ID")

    title: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = None

    items: List[OrderItemReq] = Field(
        default_factory=list, description="明细列表（可空，JSON 列存储）"
    )

    created_by: Optional[int] = Field(None, description="创建人 ID")


class OrderUpdateReq(BaseModel):
    """更新订单请求（全字段可选；仅 pending 状态可改）。"""

    company_id: Optional[int] = None
    contract_id: Optional[int] = None

    title: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = None

    items: Optional[List[OrderItemReq]] = Field(
        None, description="明细列表（不传则保留；传 [] 则清空；非空则整体替换）"
    )


class OrderCancelReq(BaseModel):
    """取消订单请求（reason 必填）。"""

    reason: str = Field(..., min_length=1, max_length=500, description="取消原因")


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------


class OrderResp(BaseModel):
    """订单响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int

    company_id: Optional[int] = None
    contract_id: Optional[int] = None

    order_no: str
    title: Optional[str] = None

    total_amount: Optional[Decimal] = None

    items: List[OrderItemResp] = Field(default_factory=list)

    status: str
    confirmed_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None

    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[int] = None


class OrderListResp(BaseModel):
    """订单分页列表响应。"""

    total: int
    page: int
    page_size: int
    items: List[OrderResp]


class OrderStatsResp(BaseModel):
    """订单统计概览。"""

    total: int
    pending: int
    confirmed: int
    delivered: int
    completed: int
    cancelled: int
    total_amount: Decimal = Field(Decimal("0"), description="所有订单 total_amount 之和")
    completed_amount: Decimal = Field(
        Decimal("0"), description="已完成订单的 total_amount 之和"
    )


__all__ = [
    "OrderCancelReq",
    "OrderCreateReq",
    "OrderItemReq",
    "OrderItemResp",
    "OrderListResp",
    "OrderResp",
    "OrderStatsResp",
    "OrderUpdateReq",
]
