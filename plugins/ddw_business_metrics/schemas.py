"""DDW 业务指标仪表盘插件 Pydantic schemas。

纯只读聚合查询，schemas 全部为响应类型。
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 趋势点 / 插件使用 / 漏斗阶段
# ---------------------------------------------------------------------------


class MetricPoint(BaseModel):
    """趋势数据点（月份 / 周标签 + 值）。"""

    label: str = Field(..., description="月份（YYYY-MM）或周（YYYY-Wxx）标签")
    value: float = Field(..., description="值（MRR 元 / WAU 人数）")


class PluginUsage(BaseModel):
    """插件使用率条目。"""

    event_type: str = Field(..., description="事件类型")
    count: int = Field(..., description="使用次数")


class FunnelStage(BaseModel):
    """漏斗阶段。"""

    stage: str = Field(..., description="阶段：leads / opportunities / orders")
    count: int = Field(..., description="该阶段数量")


# ---------------------------------------------------------------------------
# 总览
# ---------------------------------------------------------------------------


class MetricsSummary(BaseModel):
    """业务指标总览。"""

    mrr_cents: int = Field(..., description="当月 MRR（分）")
    mrr_trend: List[MetricPoint] = Field(default_factory=list, description="MRR 近 N 月趋势")
    wau: int = Field(..., description="近 7 天 WAU（周活跃用户数）")
    wau_trend: List[MetricPoint] = Field(default_factory=list, description="WAU 近 N 周趋势")
    token_usage_7d: int = Field(..., description="近 7 天 Token 消耗总量")
    plugins_top: List[PluginUsage] = Field(default_factory=list, description="插件使用率 Top N")
    funnel: List[FunnelStage] = Field(default_factory=list, description="转化漏斗")
    as_of: str = Field(..., description="数据截止时间（ISO 格式）")


# ---------------------------------------------------------------------------
# 健康检查
# ---------------------------------------------------------------------------


class HealthResp(BaseModel):
    """健康检查响应。"""

    status: str = Field("ok", description="服务状态")
    version: str = Field(..., description="插件版本")


__all__ = [
    "FunnelStage",
    "HealthResp",
    "MetricPoint",
    "MetricsSummary",
    "PluginUsage",
]
