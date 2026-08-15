from __future__ import annotations

"""DDW Token 额度管理插件 Pydantic schemas。

包含：
- TokenEntitlementCreateReq：新建额度分配
- TokenEntitlementUpdateReq：更新额度（不能改 used_tokens）
- TokenConsumeReq：消耗 tokens 请求体
- TokenEntitlementResp：详情/列表项
- TokenEntitlementListResp：分页列表
- TokenConsumeResp：消耗结果（含超量标记）
- TokenEntitlementStatsResp：统计概览
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 合法额度类型
ALLOWED_ENTITLEMENT_TYPES: tuple[str, ...] = ("platform", "custom-key", "local-llm")


def _validate_entitlement_type(v: Optional[str]) -> Optional[str]:
    """统一校验：None 透传；非 None 必须在白名单内。"""
    if v is None:
        return v
    if v not in ALLOWED_ENTITLEMENT_TYPES:
        raise ValueError(
            f"entitlement_type 必须是 {list(ALLOWED_ENTITLEMENT_TYPES)} 之一，收到: {v!r}"
        )
    return v


def _validate_masked_api_key(v: Optional[str]) -> Optional[str]:
    """校验 api_key_masked：必须已经是脱敏形式（含 ``****``），不接受明文。"""
    if v is None:
        return v
    if "****" not in v:
        raise ValueError(
            "api_key_masked 必须已是脱敏形式（如 'sk-****1234'），不接受明文"
        )
    if len(v) > 50:
        raise ValueError("api_key_masked 长度不能超过 50 字符")
    return v


# ---------------------------------------------------------------------------
# 创建
# ---------------------------------------------------------------------------


class TokenEntitlementCreateReq(BaseModel):
    """新建额度分配请求。"""

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")

    company_id: Optional[int] = Field(None, description="关联客户企业 ID（可空）")
    instance_id: Optional[int] = Field(None, description="关联安装实例 ID（可空）")

    entitlement_type: str = Field(
        ..., description="额度类型：platform / custom-key / local-llm"
    )
    allocated_tokens: int = Field(0, ge=0, description="分配额度（>=0）")
    overage_allowed: bool = Field(False, description="是否允许超量消耗")
    api_key_masked: Optional[str] = Field(
        None, max_length=50, description="客户自带 Key（必须脱敏，如 sk-****1234）"
    )
    llm_endpoint: Optional[str] = Field(
        None, max_length=500, description="本地 LLM 访问地址"
    )
    notes: Optional[str] = None
    created_by: Optional[int] = Field(None, description="创建人 user_id")

    @field_validator("entitlement_type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        coerced = _validate_entitlement_type(v)
        assert coerced is not None
        return coerced

    @field_validator("api_key_masked")
    @classmethod
    def _check_masked(cls, v: Optional[str]) -> Optional[str]:
        return _validate_masked_api_key(v)


# ---------------------------------------------------------------------------
# 更新（全字段可选；不能改 used_tokens / tenant_id）
# ---------------------------------------------------------------------------


class TokenEntitlementUpdateReq(BaseModel):
    """更新额度分配请求。

    - 不允许修改 used_tokens（仅 consume 端点能改）
    - 不允许修改 tenant_id（保持租户隔离）
    - 字段级更新：只更新传了的字段
    """

    company_id: Optional[int] = None
    instance_id: Optional[int] = None

    entitlement_type: Optional[str] = None
    allocated_tokens: Optional[int] = Field(None, ge=0)
    overage_allowed: Optional[bool] = None
    api_key_masked: Optional[str] = Field(None, max_length=50)
    llm_endpoint: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None

    @field_validator("entitlement_type")
    @classmethod
    def _check_type(cls, v: Optional[str]) -> Optional[str]:
        return _validate_entitlement_type(v)

    @field_validator("api_key_masked")
    @classmethod
    def _check_masked(cls, v: Optional[str]) -> Optional[str]:
        return _validate_masked_api_key(v)


# ---------------------------------------------------------------------------
# 消耗请求
# ---------------------------------------------------------------------------


class TokenConsumeReq(BaseModel):
    """消耗 tokens 请求体。"""

    tokens: int = Field(..., ge=1, description="本次消耗的 token 数（>=1）")


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------


class TokenEntitlementResp(BaseModel):
    """额度分配详情/列表项响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int

    company_id: Optional[int] = None
    instance_id: Optional[int] = None

    entitlement_type: str
    allocated_tokens: int
    used_tokens: int
    remaining_tokens: int
    overage_allowed: bool

    api_key_masked: Optional[str] = None
    llm_endpoint: Optional[str] = None

    notes: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[int] = None


class TokenEntitlementListResp(BaseModel):
    """额度分配分页列表响应。"""

    total: int
    page: int
    page_size: int
    items: List[TokenEntitlementResp]


class TokenConsumeResp(BaseModel):
    """消耗结果响应。"""

    id: int
    tokens_consumed: int
    allocated_tokens: int
    used_tokens: int
    remaining_tokens: int
    overage: int = Field(..., description="超量数（负数表示超量）")
    overage_allowed: bool


class TokenEntitlementStatsResp(BaseModel):
    """统计概览响应。

    - total_allocated / total_used / total_remaining
    - by_type：按 entitlement_type 分组（dict: type -> {allocated, used, count}）
    - overage_count：已发生超量的客户数（按 company_id 统计；同公司多笔合并）
    - total_count：分配记录总数
    """

    total_count: int
    total_allocated: int
    total_used: int
    total_remaining: int
    by_type: dict[str, dict[str, int]]
    overage_count: int


__all__ = [
    "ALLOWED_ENTITLEMENT_TYPES",
    "TokenConsumeReq",
    "TokenConsumeResp",
    "TokenEntitlementCreateReq",
    "TokenEntitlementListResp",
    "TokenEntitlementResp",
    "TokenEntitlementStatsResp",
    "TokenEntitlementUpdateReq",
]
