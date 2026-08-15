from __future__ import annotations

from typing import List, Optional

"""DDW 实例绑定插件 Pydantic schemas。

包含：
- InstanceCreateReq：绑定实例请求（必填 instance_type / instance_id）
- InstanceUpdateReq：更新实例请求（全字段可选）
- InstanceHeartbeatReq：心跳上报请求（可选携带 status）
- InstanceResp：实例响应
- InstanceListResp：分页列表
- InstanceStatsResp：统计概览
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 创建
# ---------------------------------------------------------------------------


class InstanceCreateReq(BaseModel):
    """绑定实例请求。

    必填：instance_type / instance_id
    company_id / license_id 二者至少传一个（业务上实例必须挂到一个主体下）
    """

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")

    company_id: Optional[int] = Field(None, description="关联客户企业 ID")
    license_id: Optional[int] = Field(None, description="关联许可证 ID")

    instance_type: str = Field(
        ..., min_length=1, max_length=20, description="实例类型：saas / on-premise"
    )
    instance_id: str = Field(
        ..., min_length=1, max_length=100, description="业务实例 ID（云端租户 ID 或本地 UUID）"
    )
    instance_name: Optional[str] = Field(None, max_length=100, description="实例显示名")
    fingerprint: Optional[str] = Field(None, max_length=200, description="实例指纹（用于校验）")

    environment: str = Field(
        "production", min_length=1, max_length=20, description="部署环境：production/staging/test"
    )
    endpoint: Optional[str] = Field(None, max_length=500, description="实例访问地址")

    created_by: Optional[int] = Field(None, description="创建人 user_id")


# ---------------------------------------------------------------------------
# 更新（全字段可选）
# ---------------------------------------------------------------------------


class InstanceUpdateReq(BaseModel):
    """更新实例请求（全字段可选；用于改名/换环境/改 endpoint 等）。"""

    instance_name: Optional[str] = Field(None, min_length=1, max_length=100)
    fingerprint: Optional[str] = Field(None, max_length=200)
    environment: Optional[str] = Field(None, min_length=1, max_length=20)
    endpoint: Optional[str] = Field(None, max_length=500)
    status: Optional[str] = Field(
        None, min_length=1, max_length=20, description="状态：active/inactive/suspended"
    )
    updated_by: Optional[int] = Field(None, description="更新人 user_id")


# ---------------------------------------------------------------------------
# 心跳
# ---------------------------------------------------------------------------


class InstanceHeartbeatReq(BaseModel):
    """心跳上报请求（可选携带 status）。"""

    status: Optional[str] = Field(
        None, min_length=1, max_length=20, description="可选：同时更新状态（active/inactive）"
    )


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------


class InstanceResp(BaseModel):
    """实例响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int

    company_id: Optional[int] = None
    license_id: Optional[int] = None

    instance_type: str
    instance_id: str
    instance_name: Optional[str] = None
    fingerprint: Optional[str] = None

    environment: str
    endpoint: Optional[str] = None

    status: str
    last_heartbeat: Optional[datetime] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[int] = None
    updated_by: Optional[int] = None


class InstanceListResp(BaseModel):
    """实例分页列表响应。"""

    total: int
    page: int
    page_size: int
    items: List[InstanceResp]


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------


class InstanceStatsResp(BaseModel):
    """实例统计概览。

    - total / 各状态计数
    - by_instance_type：按类型分组（saas / on-premise）
    - by_environment：按环境分组（production/staging/test）
    - heartbeat_alive：最近 24h 内有心跳的实例数
    """

    total: int
    active: int
    inactive: int
    suspended: int
    by_instance_type: dict[str, int]
    by_environment: dict[str, int]
    heartbeat_alive: int = Field(0, description="最近 24h 内有心跳的实例数")


__all__ = [
    "InstanceCreateReq",
    "InstanceHeartbeatReq",
    "InstanceListResp",
    "InstanceResp",
    "InstanceStatsResp",
    "InstanceUpdateReq",
]
