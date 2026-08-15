from __future__ import annotations

"""DDW 售后工单插件 Pydantic schemas。

包含：
- TicketCreateReq：新建工单请求
- TicketUpdateReq：更新工单请求（全字段可选；status 不在其中，单独走状态机）
- TicketAssignReq：分配处理人请求
- TicketResolveReq：解决工单请求（resolution 必填）
- TicketResp：工单响应
- TicketListResp：分页列表
- TicketStatsResp：统计概览
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 合法值枚举（与 manifest.yaml 保持一致）
# ---------------------------------------------------------------------------

CATEGORIES: List[str] = ["bug", "feature", "question", "complaint", "other"]
PRIORITIES: List[str] = ["low", "normal", "high", "urgent"]
STATUSES: List[str] = ["open", "in_progress", "resolved", "closed"]


# ---------------------------------------------------------------------------
# 创建
# ---------------------------------------------------------------------------


class TicketCreateReq(BaseModel):
    """新建工单请求（status 默认 open，ticket_no 自动生成 TKT-YYYYMMDD-NNN）。"""

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")

    company_id: Optional[int] = Field(None, description="关联客户企业 ID")
    instance_id: Optional[int] = Field(None, description="关联客户实例 ID")

    title: str = Field(..., min_length=1, max_length=200, description="工单标题")
    description: str = Field(..., min_length=1, description="工单详细描述")

    category: str = Field(
        "other",
        description="工单分类（bug/feature/question/complaint/other）",
    )
    priority: str = Field(
        "normal", description="优先级（low/normal/high/urgent）"
    )

    assigned_to: Optional[int] = Field(None, description="处理人 ID（可后续分配）")
    created_by: Optional[int] = Field(None, description="创建人 ID")


# ---------------------------------------------------------------------------
# 更新（全字段可选；status 排除，走专门状态机端点）
# ---------------------------------------------------------------------------


class TicketUpdateReq(BaseModel):
    """更新工单请求（全字段可选）。

    业务规则（service 层校验）：
    - status 不在本请求中，修改状态走状态机端点
    - title / description / category / priority / assigned_to 任何状态下可改
    """

    company_id: Optional[int] = None
    instance_id: Optional[int] = None

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None

    assigned_to: Optional[int] = None
    resolution: Optional[str] = None


# ---------------------------------------------------------------------------
# 状态机迁移请求
# ---------------------------------------------------------------------------


class TicketAssignReq(BaseModel):
    """分配处理人请求（assigned_to 必填）。"""

    assigned_to: int = Field(..., ge=1, description="处理人 ID（必填）")


class TicketResolveReq(BaseModel):
    """解决工单请求（resolution 必填）。"""

    resolution: str = Field(..., min_length=1, description="解决方案（必填）")


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------


class TicketResp(BaseModel):
    """工单响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int

    company_id: Optional[int] = None
    instance_id: Optional[int] = None

    ticket_no: str
    title: str

    category: str
    priority: str

    description: str
    resolution: Optional[str] = None

    assigned_to: Optional[int] = None

    status: str
    resolved_at: Optional[datetime] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[int] = None


class TicketListResp(BaseModel):
    """工单分页列表响应。"""

    total: int
    page: int
    page_size: int
    items: List[TicketResp]


class TicketStatsResp(BaseModel):
    """工单统计概览。

    - 各状态计数（保证所有合法 status 都有键，缺省为 0）
    - 按 category 分组
    - 按 priority 分组
    """

    total: int
    open: int
    in_progress: int
    resolved: int
    closed: int
    by_category: dict[str, int]
    by_priority: dict[str, int]


__all__ = [
    "CATEGORIES",
    "PRIORITIES",
    "STATUSES",
    "TicketAssignReq",
    "TicketCreateReq",
    "TicketListResp",
    "TicketResolveReq",
    "TicketResp",
    "TicketStatsResp",
    "TicketUpdateReq",
]
