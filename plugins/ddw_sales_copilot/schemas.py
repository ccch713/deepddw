from __future__ import annotations

from typing import List, Optional

"""DDW 销售端 AI 副驾驶插件 Pydantic schemas。

本插件为 AI 能力聚合层，所有端点都遵循：

- 请求体（Req）：仅含必要 ID（opportunity_id / company_id / user_id / date 等）
- 响应体（Resp）：包含 ``tenant_id`` + LLM 输出（``reasoning`` / ``alert`` / ``report``）
  + 确定性计算的中间结果（metrics / risk_factors / actions 等）

所有 schema 都包含 ``tenant_id: int = Field(1, ge=1)`` 以保持与 P0/P1/P2/P3 其它插件一致。
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 通用 tenant 字段
# ---------------------------------------------------------------------------


class _TenantMixin(BaseModel):
    """所有 copilot 响应都携带租户 ID。"""

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")


# ---------------------------------------------------------------------------
# 1. Stage Suggestion（商机阶段建议）
# ---------------------------------------------------------------------------


class StageSuggestionReq(BaseModel):
    """阶段建议请求。"""

    opportunity_id: int = Field(..., ge=1, description="商机 ID")
    tenant_id: int = Field(1, ge=1, description="租户 ID")


class StageSuggestionResp(_TenantMixin):
    """阶段建议响应。

    - ``current_stage`` / ``suggested_stage`` 使用 P0-3 的阶段编码
      （initial_contact / demand_confirmation / proposal_submitted /
      quotation_sent / negotiation / contract_pending / won / lost）
    - ``reasoning`` 直接透传 LLM 输出（默认 echo backend → 含 echo 标识）
    """

    opportunity_id: int = Field(..., description="商机 ID")
    opportunity_name: str = Field("", description="商机名称（便于审计）")
    current_stage: str = Field(..., description="当前阶段编码")
    current_stage_label: str = Field("", description="当前阶段中文标签")
    suggested_stage: str = Field(..., description="建议推进到的阶段编码")
    suggested_stage_label: str = Field("", description="建议阶段中文标签")
    probability: int = Field(0, description="建议阶段对应的默认成单概率（%）")
    reasoning: str = Field("", description="LLM 推理输出（透传）")
    recent_notes_count: int = Field(0, description="近 N 条沟通记录条数")
    last_activity_at: Optional[datetime] = Field(None, description="最近一次活动时间")


# ---------------------------------------------------------------------------
# 2. Risk Alert（客户风险提示）
# ---------------------------------------------------------------------------


class RiskAlertReq(BaseModel):
    """风险提示请求：opportunity_id 与 company_id 至少传一个。"""

    opportunity_id: Optional[int] = Field(None, ge=1, description="商机 ID（与 company_id 二选一）")
    company_id: Optional[int] = Field(None, ge=1, description="企业 ID（与 opportunity_id 二选一）")
    tenant_id: int = Field(1, ge=1, description="租户 ID")


class RiskAlertResp(_TenantMixin):
    """风险提示响应。

    ``risk_level`` 取值：``low`` / ``medium`` / ``high``
    ``risk_factors`` 列出命中的规则编码，便于前端做可解释性提示。
    """

    opportunity_id: Optional[int] = Field(None, description="商机 ID（如有）")
    company_id: Optional[int] = Field(None, description="企业 ID（如有）")
    opportunity_name: str = Field("", description="商机名称（便于审计）")
    company_name: str = Field("", description="企业名称（便于审计）")
    risk_level: str = Field(..., description="风险等级：low / medium / high")
    risk_score: float = Field(0.0, description="风险分数 [0, 1]（规则加权平均）")
    risk_factors: List[str] = Field(default_factory=list, description="命中的风险因素编码列表")
    stale_days: int = Field(0, description="距离最近一次活动天数")
    last_activity_at: Optional[datetime] = Field(None, description="最近一次活动时间")
    alert: str = Field("", description="LLM 输出的综合告警文本（透传）")


# ---------------------------------------------------------------------------
# 3. Action Suggestion（行动建议）
# ---------------------------------------------------------------------------


class ActionSuggestionReq(BaseModel):
    """行动建议请求。"""

    opportunity_id: int = Field(..., ge=1, description="商机 ID")
    tenant_id: int = Field(1, ge=1, description="租户 ID")


class ActionSuggestionResp(_TenantMixin):
    """行动建议响应。

    ``actions`` 是 LLM 推荐的 3~5 条可执行动作（按优先级倒序）；
    ``priority`` 是综合优先级（high/medium/low），由 LLM 给出。
    """

    opportunity_id: int = Field(..., description="商机 ID")
    opportunity_name: str = Field("", description="商机名称")
    current_stage: str = Field("", description="当前阶段编码")
    current_stage_label: str = Field("", description="当前阶段中文标签")
    priority: str = Field("medium", description="综合优先级：high / medium / low")
    actions: List[str] = Field(default_factory=list, description="建议动作清单（按优先级倒序）")
    reasoning: str = Field("", description="LLM 推理输出（透传）")
    context_summary: dict = Field(
        default_factory=dict,
        description="确定性计算的上下文指标（notes_count / quotations_count / stale_days）",
    )


# ---------------------------------------------------------------------------
# 4. Daily Report（销售日报）
# ---------------------------------------------------------------------------


class DailyReportReq(BaseModel):
    """销售日报请求。"""

    user_id: int = Field(..., ge=1, description="销售员 user_id")
    report_date: date = Field(
        ...,
        description="日期 YYYY-MM-DD",
        validation_alias="date",
        serialization_alias="date",
    )
    tenant_id: int = Field(1, ge=1, description="租户 ID")

    model_config = {"populate_by_name": True}


class DailyMetrics(BaseModel):
    """单日工作指标。"""

    opportunities_created: int = Field(0, description="当日新增商机数")
    opportunities_updated: int = Field(0, description="当日有更新的商机数")
    new_contacts: int = Field(0, description="当日新增联系人数")
    new_quotations: int = Field(0, description="当日新增报价单数")
    new_notes: int = Field(0, description="当日新增沟通记录数")
    notes_visit: int = Field(0, description="其中拜访类记录数")
    notes_call: int = Field(0, description="其中电话类记录数")
    notes_meeting: int = Field(0, description="其中会议类记录数")


class DailyReportResp(_TenantMixin):
    """销售日报响应。"""

    user_id: int = Field(..., description="销售员 user_id")
    report_date: date = Field(
        ...,
        description="日报对应日期",
        validation_alias="date",
        serialization_alias="date",
    )
    metrics: DailyMetrics = Field(..., description="当日工作指标聚合")
    highlights: List[str] = Field(default_factory=list, description="当日亮点（确定性提炼）")
    report: str = Field("", description="LLM 生成的结构化日报正文（透传）")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# 5. Weekly Report（销售周报）
# ---------------------------------------------------------------------------


class WeeklyReportReq(BaseModel):
    """销售周报请求。"""

    user_id: int = Field(..., ge=1, description="销售员 user_id")
    week_start: date = Field(..., description="周一日期 YYYY-MM-DD")
    tenant_id: int = Field(1, ge=1, description="租户 ID")

    # 注：Pydantic 2 不允许字段名与类型名同名，
    # 所以日报的 date 字段使用 alias="date" + populate_by_name=True。
    # 周报字段名与类型不冲突，不需此配置。


class WeeklyMetrics(BaseModel):
    """单周工作指标。"""

    opportunities_created: int = Field(0, description="本周新增商机数")
    opportunities_updated: int = Field(0, description="本周有更新的商机数")
    opportunities_won: int = Field(0, description="本周成交商机数")
    opportunities_lost: int = Field(0, description="本周丢单商机数")
    new_contacts: int = Field(0, description="本周新增联系人数")
    new_quotations: int = Field(0, description="本周新增报价单数")
    new_notes: int = Field(0, description="本周新增沟通记录数")
    notes_visit: int = Field(0, description="其中拜访类记录数")
    notes_call: int = Field(0, description="其中电话类记录数")
    notes_meeting: int = Field(0, description="其中会议类记录数")


class WeeklyReportResp(_TenantMixin):
    """销售周报响应。"""

    user_id: int = Field(..., description="销售员 user_id")
    week_start: date = Field(..., description="周报起始日（周一）")
    week_end: date = Field(..., description="周报结束日（周日）")
    metrics: WeeklyMetrics = Field(..., description="本周工作指标聚合")
    highlights: List[str] = Field(default_factory=list, description="本周亮点（确定性提炼）")
    report: str = Field("", description="LLM 生成的结构化周报正文（透传）")


__all__ = [
    "ActionSuggestionReq",
    "ActionSuggestionResp",
    "DailyMetrics",
    "DailyReportReq",
    "DailyReportResp",
    "RiskAlertReq",
    "RiskAlertResp",
    "StageSuggestionReq",
    "StageSuggestionResp",
    "WeeklyMetrics",
    "WeeklyReportReq",
    "WeeklyReportResp",
]
