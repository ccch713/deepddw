from __future__ import annotations

"""DDW 合同中心插件 Pydantic schemas。

包含：
- ContractCreateReq：创建合同请求
- ContractUpdateReq：更新合同请求（全字段可选）
- ContractResp：合同响应
- ContractListResp：分页列表
- ContractStatsResp：统计概览
- RejectReq / TerminateReq：状态机迁移的辅助请求（reason 必填）
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 创建 / 更新
# ---------------------------------------------------------------------------


class ContractCreateReq(BaseModel):
    """新建合同请求（状态默认为 draft）。"""

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")

    company_id: Optional[int] = Field(None, description="关联客户企业 ID")
    contact_id: Optional[int] = Field(None, description="关联联系人 ID")
    opportunity_id: Optional[int] = Field(None, description="关联商机 ID")
    quotation_id: Optional[int] = Field(None, description="关联报价单 ID")

    title: Optional[str] = Field(None, max_length=200, description="合同标题")
    contract_type: str = Field(
        "standard", max_length=30, description="合同类型：standard/framework/supplementary"
    )
    total_amount: Optional[Decimal] = Field(None, ge=0, description="合同总金额")
    currency: str = Field("CNY", min_length=1, max_length=10, description="币种")

    effective_from: Optional[date] = Field(None, description="生效起始日期")
    effective_to: Optional[date] = Field(None, description="生效截止日期")

    payment_terms: Optional[str] = Field(None, description="付款条款")
    deliverables: Optional[str] = Field(None, description="交付物说明")
    sla: Optional[str] = Field(None, description="SLA / 服务水平承诺")
    attachments: Optional[List[str]] = Field(
        default=None, description="附件 URL 列表"
    )
    notes: Optional[str] = Field(None, description="备注")

    created_by: Optional[int] = Field(None, description="创建人 ID")


class ContractUpdateReq(BaseModel):
    """更新合同请求（全字段可选）。

    业务规则（service 层校验）：仅 draft / rejected 状态的合同允许修改。
    """

    company_id: Optional[int] = None
    contact_id: Optional[int] = None
    opportunity_id: Optional[int] = None
    quotation_id: Optional[int] = None

    title: Optional[str] = Field(None, max_length=200)
    contract_type: Optional[str] = Field(None, max_length=30)
    total_amount: Optional[Decimal] = Field(None, ge=0)
    currency: Optional[str] = Field(None, min_length=1, max_length=10)

    effective_from: Optional[date] = None
    effective_to: Optional[date] = None

    payment_terms: Optional[str] = None
    deliverables: Optional[str] = None
    sla: Optional[str] = None
    attachments: Optional[List[str]] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# 状态机迁移请求
# ---------------------------------------------------------------------------


class RejectReq(BaseModel):
    """驳回请求（reason 必填）。"""

    reason: str = Field(..., min_length=1, description="驳回原因（必填）")


class TerminateReq(BaseModel):
    """终止请求（reason 必填）。"""

    reason: str = Field(..., min_length=1, description="终止原因（必填）")


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------


class ContractResp(BaseModel):
    """合同响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int

    company_id: Optional[int] = None
    contact_id: Optional[int] = None
    opportunity_id: Optional[int] = None
    quotation_id: Optional[int] = None

    contract_no: str
    title: Optional[str] = None

    contract_type: str
    total_amount: Optional[Decimal] = None
    currency: str

    signed_at: Optional[datetime] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None

    payment_terms: Optional[str] = None
    deliverables: Optional[str] = None
    sla: Optional[str] = None

    attachments: Optional[List[str]] = None
    notes: Optional[str] = None

    version: int
    status: str

    approved_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    reject_reason: Optional[str] = None
    activated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    terminated_at: Optional[datetime] = None
    terminate_reason: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[int] = None


class ContractListResp(BaseModel):
    """合同分页列表响应。"""

    total: int
    page: int
    page_size: int
    items: List[ContractResp]


class ContractStatsResp(BaseModel):
    """合同统计概览。

    - 各状态计数（保证所有合法 status 都有键，缺省为 0）
    - 按 contract_type 分组计数
    - 按 status 分组计数
    - 总金额 / 激活 / 完结合同金额
    """

    total: int
    draft: int
    pending_approval: int
    approved: int
    signed: int
    active: int
    completed: int
    terminated: int
    rejected: int
    by_type: dict[str, int]
    by_status: dict[str, int]
    total_amount: Decimal = Field(Decimal("0"), description="所有合同 total_amount 之和")
    active_amount: Decimal = Field(Decimal("0"), description="激活合同的 total_amount 之和")
    completed_amount: Decimal = Field(Decimal("0"), description="已完结合同的 total_amount 之和")


__all__ = [
    "ContractCreateReq",
    "ContractListResp",
    "ContractResp",
    "ContractStatsResp",
    "ContractUpdateReq",
    "RejectReq",
    "TerminateReq",
]
