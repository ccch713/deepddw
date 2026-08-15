from __future__ import annotations

from typing import List, Optional

"""DDW 账号/租户/实例映射插件 Pydantic schemas。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# 枚举常量（与 manifest.yaml / models.py 注释保持一致）
# ---------------------------------------------------------------------------

LINK_TYPES = {"user", "saas_tenant", "on_premise_instance"}
STATUSES = {"active", "inactive"}


# ---------------------------------------------------------------------------
# 创建
# ---------------------------------------------------------------------------


class AccountLinkCreateReq(BaseModel):
    """新建账号链接请求。"""

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")

    # 关联（可空）
    company_id: Optional[int] = Field(None, description="关联客户企业 ID（可空）")

    # 分类
    link_type: str = Field(
        ..., description="链接类型：user / saas_tenant / on_premise_instance"
    )
    external_id: str = Field(..., min_length=1, max_length=100, description="外部账号 ID")
    external_name: Optional[str] = Field(None, max_length=100, description="外部账号名称")

    # 扩展
    metadata_json: Optional[dict] = Field(
        None, description="扩展元数据（如实例规格、租户 region）"
    )

    # 审计
    created_by: Optional[int] = None

    @field_validator("link_type")
    @classmethod
    def _check_link_type(cls, v: str) -> str:
        if v not in LINK_TYPES:
            raise ValueError(f"link_type 必须是 {sorted(LINK_TYPES)} 之一，得到 {v!r}")
        return v


# ---------------------------------------------------------------------------
# 更新（全字段可选）
# ---------------------------------------------------------------------------


class AccountLinkUpdateReq(BaseModel):
    """更新账号链接请求（全字段可选）。"""

    external_name: Optional[str] = Field(None, max_length=100)
    metadata_json: Optional[dict] = None
    status: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in STATUSES:
            raise ValueError(f"status 必须是 {sorted(STATUSES)} 之一，得到 {v!r}")
        return v


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------


class AccountLinkResp(BaseModel):
    """账号链接响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int

    company_id: Optional[int] = None

    link_type: str
    external_id: str
    external_name: Optional[str] = None

    metadata_json: Optional[dict] = None

    status: str

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[int] = None


class AccountLinkListResp(BaseModel):
    """账号链接分页列表响应。"""

    total: int
    page: int
    page_size: int
    items: List[AccountLinkResp]


class AccountLinkStatsResp(BaseModel):
    """账号链接统计概览。"""

    total: int
    active: int
    inactive: int
    by_link_type: dict[str, int]


__all__ = [
    "LINK_TYPES",
    "STATUSES",
    "AccountLinkCreateReq",
    "AccountLinkListResp",
    "AccountLinkResp",
    "AccountLinkStatsResp",
    "AccountLinkUpdateReq",
]
