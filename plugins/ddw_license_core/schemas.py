from __future__ import annotations

from typing import List, Optional

"""DDW 许可证管理插件 Pydantic schemas。

包含：
- LicenseCreateReq：新建许可证（必填 license_type / valid_from / valid_to）
- LicenseUpdateReq：更新许可证（仅 active/suspended 状态可改）
- LicenseRenewalReq：续费请求
- LicenseResp：许可证响应
- LicenseListResp：分页列表
- LicenseStatsResp：统计概览
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 创建
# ---------------------------------------------------------------------------


class LicenseCreateReq(BaseModel):
    """新建许可证请求。

    license_no 由服务端自动生成（LIC-YYYYMMDD-NNN），无需客户端传入。
    """

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")

    company_id: Optional[int] = Field(None, description="关联客户企业 ID")

    license_type: str = Field(
        ..., min_length=1, max_length=20, description="许可证类型：trial / formal / renewal"
    )
    product_ids: Optional[List[int]] = Field(
        default=None, description="关联产品 ID 列表"
    )
    plugin_entitlements: Optional[List[str]] = Field(
        default=None, description="插件授权清单（plugin_code 列表）"
    )

    max_users: int = Field(5, ge=1, description="最大用户数（>=1）")
    max_nodes: int = Field(1, ge=1, description="最大节点数（>=1）")

    valid_from: date = Field(..., description="生效起始日期")
    valid_to: date = Field(..., description="生效截止日期")

    notes: Optional[str] = None
    created_by: Optional[int] = Field(None, description="创建人 user_id")


# ---------------------------------------------------------------------------
# 更新（全字段可选；仅 active / suspended 状态可改）
# ---------------------------------------------------------------------------


class LicenseUpdateReq(BaseModel):
    """更新许可证请求（全字段可选；仅 active / suspended 状态可改）。"""

    license_type: Optional[str] = Field(None, min_length=1, max_length=20)
    product_ids: Optional[List[int]] = None
    plugin_entitlements: Optional[List[str]] = None
    max_users: Optional[int] = Field(None, ge=1)
    max_nodes: Optional[int] = Field(None, ge=1)
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# 续费
# ---------------------------------------------------------------------------


class LicenseRenewalReq(BaseModel):
    """续费请求。

    不传 valid_from / valid_to 时，新许可证默认：
    - valid_from = 今天
    - valid_to   = valid_from + 1 年
    """

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")
    valid_from: Optional[date] = Field(None, description="新许可证起始日期；不传=今天")
    valid_to: Optional[date] = Field(None, description="新许可证截止日期；不传=valid_from+1y")
    max_users: Optional[int] = Field(None, ge=1)
    max_nodes: Optional[int] = Field(None, ge=1)
    product_ids: Optional[List[int]] = None
    plugin_entitlements: Optional[List[str]] = None
    notes: Optional[str] = None
    created_by: Optional[int] = Field(None, description="创建人 user_id")


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------


class LicenseResp(BaseModel):
    """许可证响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int

    company_id: Optional[int] = None
    parent_license_id: Optional[int] = None

    license_no: str
    license_type: str

    product_ids: Optional[List[int]] = None
    plugin_entitlements: Optional[List[str]] = None

    max_users: int
    max_nodes: int

    valid_from: date
    valid_to: date

    status: str
    notes: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[int] = None


class LicenseListResp(BaseModel):
    """许可证分页列表响应。"""

    total: int
    page: int
    page_size: int
    items: List[LicenseResp]


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------


class LicenseStatsResp(BaseModel):
    """许可证统计概览。

    - total / 各状态计数
    - by_license_type：按 license_type 分组计数
    - active_total_users / active_total_nodes：当前 active 许可证的容量合计
    """

    total: int
    active: int
    expired: int
    suspended: int
    revoked: int
    renewed: int
    by_license_type: dict[str, int]
    active_total_users: int = Field(0, description="active 许可证 max_users 之和")
    active_total_nodes: int = Field(0, description="active 许可证 max_nodes 之和")


__all__ = [
    "LicenseCreateReq",
    "LicenseListResp",
    "LicenseRenewalReq",
    "LicenseResp",
    "LicenseStatsResp",
    "LicenseUpdateReq",
]
