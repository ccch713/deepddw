from __future__ import annotations

"""DDW 商机管理插件 Pydantic schemas。"""

from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 创建
# ---------------------------------------------------------------------------


class OpportunityCreateReq(BaseModel):
    """新建商机请求。"""

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")
    name: str = Field(..., min_length=1, max_length=200, description="商机名称")
    company_id: Optional[int] = Field(None, description="关联企业 ID")
    contact_id: Optional[int] = Field(None, description="关联联系人 ID")
    source: Optional[str] = Field(None, max_length=50, description="来源：直销/经销商/官网/展会/转介绍")
    owner_id: Optional[int] = Field(None, description="负责人用户 ID")
    estimated_amount: Optional[Decimal] = Field(None, description="预计金额")
    stage: Optional[str] = Field(
        "initial_contact",
        max_length=30,
        description="初始阶段，默认 initial_contact",
    )
    probability: Optional[int] = Field(10, ge=0, le=100, description="成交概率 0-100")
    expected_close_date: Optional[date] = Field(None, description="预计成交日期")
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    created_by: Optional[int] = Field(None, description="创建人用户 ID")


# ---------------------------------------------------------------------------
# 更新（全字段可选）
# ---------------------------------------------------------------------------


class OpportunityUpdateReq(BaseModel):
    """更新商机请求（所有字段可选）。"""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    company_id: Optional[int] = None
    contact_id: Optional[int] = None
    source: Optional[str] = Field(None, max_length=50)
    owner_id: Optional[int] = None
    estimated_amount: Optional[Decimal] = None
    expected_close_date: Optional[date] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    probability: Optional[int] = Field(None, ge=0, le=100)
    status: Optional[str] = Field(None, description="状态：open/won/lost/closed")


# ---------------------------------------------------------------------------
# 阶段更新
# ---------------------------------------------------------------------------


class StageUpdateReq(BaseModel):
    """更新商机阶段（自动同步 probability）。"""

    stage: str = Field(..., min_length=1, max_length=30, description="目标阶段")


# ---------------------------------------------------------------------------
# 标记丢单
# ---------------------------------------------------------------------------


class MarkLostReq(BaseModel):
    """标记丢单（lost_reason 必填）。"""

    lost_reason: str = Field(..., min_length=1, max_length=500, description="丢单原因")


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------


class OpportunityResp(BaseModel):
    """商机响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int

    company_id: Optional[int] = None
    contact_id: Optional[int] = None

    name: str
    source: Optional[str] = None
    owner_id: Optional[int] = None

    estimated_amount: Optional[Decimal] = None
    stage: str
    probability: int

    expected_close_date: Optional[date] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None

    status: str
    won_at: Optional[datetime] = None
    lost_reason: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[int] = None


class OpportunityListResp(BaseModel):
    """商机分页列表响应。"""

    total: int
    page: int
    page_size: int
    items: List[OpportunityResp]


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------


class StageFunnelItem(BaseModel):
    """单个阶段的漏斗数据。"""

    stage: str
    count: int
    total_amount: Decimal


class OpportunityFunnelResp(BaseModel):
    """商机漏斗统计响应。"""

    stages: List[StageFunnelItem]
    total: int
    total_amount: Decimal


class OpportunityStatsResp(BaseModel):
    """商机统计概览响应。"""

    total: int
    open: int
    won: int
    lost: int
    closed: int
    total_amount: Decimal
    won_amount: Decimal
    by_stage: Dict[str, int]
    by_source: Dict[str, int]
    by_status: Dict[str, int]


__all__ = [
    "MarkLostReq",
    "OpportunityCreateReq",
    "OpportunityFunnelResp",
    "OpportunityListResp",
    "OpportunityResp",
    "OpportunityStatsResp",
    "OpportunityUpdateReq",
    "StageFunnelItem",
    "StageUpdateReq",
]
