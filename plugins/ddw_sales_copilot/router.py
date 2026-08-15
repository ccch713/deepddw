from __future__ import annotations

"""DDW 销售端 AI 副驾驶插件 API 路由。

API 端点（6 个）：
  健康：      GET  /health
  阶段建议：  POST /copilot/stage-suggestion
  风险提示：  POST /copilot/risk-alert
  行动建议：  POST /copilot/action-suggestion
  销售日报：  POST /copilot/daily-report
  销售周报：  POST /copilot/weekly-report

所有 POST 端点都接收 Pydantic Body，跨插件只读查询全部走
``bypass_tenant_filter()`` 上下文（与 P0-5 ddw_sales_dashboard 一致）。
"""

import logging

from fastapi import APIRouter, HTTPException

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .schemas import (
    ActionSuggestionReq,
    ActionSuggestionResp,
    DailyReportReq,
    DailyReportResp,
    RiskAlertReq,
    RiskAlertResp,
    StageSuggestionReq,
    StageSuggestionResp,
    WeeklyReportReq,
    WeeklyReportResp,
)
from .services import CopilotService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造销售端 AI 副驾驶路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-sales-copilot",
        tags=["ddw-sales-copilot"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict:
        return {
            "plugin": "ddw-sales-copilot",
            "version": "1.0.0",
            "status": "ok",
        }

    # -----------------------------------------------------------------------
    # 1. 阶段建议
    # -----------------------------------------------------------------------
    @router.post("/copilot/stage-suggestion", response_model=StageSuggestionResp)
    async def stage_suggestion(data: StageSuggestionReq) -> StageSuggestionResp:
        """基于商机 + 最近沟通记录，LLM 推荐下一阶段。

        - 找不到商机 → 404
        - 推理失败 → 降级为 echo 字符串（不抛异常）
        """
        async with session_scope() as db, bypass_tenant_filter():
            svc = CopilotService(db)
            result = await svc.stage_suggestion(
                opportunity_id=data.opportunity_id,
                tenant_id=data.tenant_id,
            )
            if result is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"opportunity {data.opportunity_id} not found in tenant {data.tenant_id}",
                )
            return result

    # -----------------------------------------------------------------------
    # 2. 风险提示
    # -----------------------------------------------------------------------
    @router.post("/copilot/risk-alert", response_model=RiskAlertResp)
    async def risk_alert(data: RiskAlertReq) -> RiskAlertResp:
        """风险提示：``opportunity_id`` / ``company_id`` 至少传一个。"""
        if data.opportunity_id is None and data.company_id is None:
            raise HTTPException(
                status_code=400,
                detail="opportunity_id and company_id are both empty; please provide one",
            )
        async with session_scope() as db, bypass_tenant_filter():
            svc = CopilotService(db)
            result = await svc.risk_alert(
                opportunity_id=data.opportunity_id,
                company_id=data.company_id,
                tenant_id=data.tenant_id,
            )
            if result is None:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"opportunity {data.opportunity_id} or company {data.company_id} not found"
                    ),
                )
            return result

    # -----------------------------------------------------------------------
    # 3. 行动建议
    # -----------------------------------------------------------------------
    @router.post("/copilot/action-suggestion", response_model=ActionSuggestionResp)
    async def action_suggestion(data: ActionSuggestionReq) -> ActionSuggestionResp:
        """行动建议：基于商机 + 拜访 + 报价，生成 3~5 条可执行动作。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = CopilotService(db)
            result = await svc.action_suggestion(
                opportunity_id=data.opportunity_id,
                tenant_id=data.tenant_id,
            )
            if result is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"opportunity {data.opportunity_id} not found in tenant {data.tenant_id}",
                )
            return result

    # -----------------------------------------------------------------------
    # 4. 销售日报
    # -----------------------------------------------------------------------
    @router.post("/copilot/daily-report", response_model=DailyReportResp)
    async def daily_report(data: DailyReportReq) -> DailyReportResp:
        """销售日报：聚合某销售当日工作指标 + LLM 生成结构化日报。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = CopilotService(db)
            return await svc.daily_report(
                user_id=data.user_id,
                day=data.report_date,
                tenant_id=data.tenant_id,
            )

    # -----------------------------------------------------------------------
    # 5. 销售周报
    # -----------------------------------------------------------------------
    @router.post("/copilot/weekly-report", response_model=WeeklyReportResp)
    async def weekly_report(data: WeeklyReportReq) -> WeeklyReportResp:
        """销售周报：聚合某销售本周工作指标 + LLM 生成结构化周报。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = CopilotService(db)
            return await svc.weekly_report(
                user_id=data.user_id,
                week_start=data.week_start,
                tenant_id=data.tenant_id,
            )

    return router


__all__ = ["build_router"]
