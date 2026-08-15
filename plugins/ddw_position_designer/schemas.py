"""DDW 岗位设计器 Pydantic schemas。"""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# DecisionRight
# ---------------------------------------------------------------------------

DecisionTypeStr = Literal["auto", "suggest", "human", "escalate"]


class DecisionRightBase(BaseModel):
    scenario: str = Field(..., min_length=1, max_length=200, description="业务场景")
    human_right: str = Field(..., min_length=1, max_length=200, description="人类权限")
    agent_right: str = Field(..., min_length=1, max_length=200, description="Agent 权限")
    decision_type: DecisionTypeStr = Field("suggest", description="决策类型")


class DecisionRightResp(DecisionRightBase):
    pass


# ---------------------------------------------------------------------------
# PositionDesign
# ---------------------------------------------------------------------------


class PositionDesignBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="岗位名称")
    department: Optional[str] = Field(None, max_length=100, description="所属部门")
    report_to: Optional[str] = Field(None, max_length=100, description="汇报对象")
    company: Optional[str] = Field(None, max_length=200, description="公司/组织")
    description: Optional[str] = Field(None, description="岗位描述（传统 JD 兼容）")

    outcomes: List[str] = Field(default_factory=list, description="业务结果列表")
    human_responsibilities: List[str] = Field(default_factory=list, description="人的责任列表")
    agent_stack: List[str] = Field(default_factory=list, description="Agent 组合列表")
    decision_rights: List[DecisionRightBase] = Field(default_factory=list, description="决策权限矩阵")

    human_capability: Optional[str] = Field(None, description="人类核心能力要求")
    agent_capability: Optional[str] = Field(None, description="Agent 能力边界")
    handoff_protocol: Optional[str] = Field(None, description="人机交接协议")
    risk_controls: List[str] = Field(default_factory=list, description="风控措施列表")

    tags: Optional[List[str]] = Field(None, description="扩展标签")


class PositionDesignCreateReq(PositionDesignBase):
    tenant_id: int = Field(1, ge=1, description="租户 ID")


class PositionDesignUpdateReq(BaseModel):
    """更新岗位设计请求（所有字段可选）。"""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    department: Optional[str] = Field(None, max_length=100)
    report_to: Optional[str] = Field(None, max_length=100)
    company: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    outcomes: Optional[List[str]] = None
    human_responsibilities: Optional[List[str]] = None
    agent_stack: Optional[List[str]] = None
    decision_rights: Optional[List[DecisionRightBase]] = None
    human_capability: Optional[str] = None
    agent_capability: Optional[str] = None
    handoff_protocol: Optional[str] = None
    risk_controls: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    status: Optional[Literal["draft", "active", "archived"]] = None


class PositionDesignResp(ORMModel):
    """岗位设计详情响应。"""

    id: int
    tenant_id: int
    name: str
    department: Optional[str] = None
    report_to: Optional[str] = None
    company: Optional[str] = None
    description: Optional[str] = None
    outcomes: List[str] = []
    human_responsibilities: List[str] = []
    agent_stack: List[str] = []
    decision_rights: List[DecisionRightResp] = []
    human_capability: Optional[str] = None
    agent_capability: Optional[str] = None
    handoff_protocol: Optional[str] = None
    risk_controls: List[str] = []
    status: str
    version: int
    tags: List[str] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PositionDesignListResp(BaseModel):
    items: List[PositionDesignResp]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Health / Config
# ---------------------------------------------------------------------------


class HealthResp(BaseModel):
    status: str
    plugin: str
    version: str
    positions_count: int


class PluginConfigResp(BaseModel):
    decision_types: List[dict]  # [{value, label}]
    default_agents: List[str]
    standard_departments: List[str]
    decision_routing_weights: dict
