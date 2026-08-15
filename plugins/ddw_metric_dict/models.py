"""B9 指标口径字典 - Pydantic 模型"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MetricFormula(BaseModel):
    """单条口径定义"""
    caliber_id: str
    formula: str
    data_source: str = ""
    update_frequency: str = "daily"


class MetricDefinition(BaseModel):
    """指标定义（含多条口径）"""
    metric_id: str
    name: str
    calibers: list[MetricFormula] = Field(default_factory=list)
    default_caliber_id: str = ""


class MetricRouteRequest(BaseModel):
    """口径路由请求"""
    metric_name: str
    department: str = ""
    context: dict[str, Any] = Field(default_factory=dict)


class MetricRouteResponse(BaseModel):
    """口径路由响应"""
    metric_id: str
    metric_name: str
    selected_caliber: MetricFormula
    reason: str = ""


class MetricAdjudicationRequest(BaseModel):
    """冲突裁决请求"""
    metric_name: str
    department_a: str
    department_b: str


class MetricAdjudicationResult(BaseModel):
    """冲突裁决结果"""
    metric_id: str
    metric_name: str
    conflict_description: str
    suggested_caliber: MetricFormula
    suggestion_reason: str = ""
