"""KPI API 路由"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter
from plugins.ddw_kpi.models import KpiRecord, KpiRule


class RuleReq(BaseModel):
    rule_name: str
    subject: str = ""
    weight: float = 1.0
    threshold: float = 60.0
    formula: str = "average_score"

async def list_rules() -> List[Dict[str, Any]]:
    async with session_scope() as s, bypass_tenant_filter():
        rows = (await s.execute(select(KpiRule))).scalars().all()
    return [{"id": r.id, "rule_name": r.rule_name, "subject": r.subject, "weight": r.weight, "enabled": r.enabled} for r in rows]

async def create_rule(req: RuleReq) -> Dict[str, Any]:
    async with session_scope() as s, bypass_tenant_filter():
        rule = KpiRule(rule_name=req.rule_name, subject=req.subject, weight=req.weight, threshold=req.threshold, formula=req.formula)
        s.add(rule)
        await s.commit()
        await s.refresh(rule)
    return {"id": rule.id, "rule_name": rule.rule_name}

async def dashboard() -> Dict[str, Any]:
    async with session_scope() as s, bypass_tenant_filter():
        records = (await s.execute(select(KpiRecord))).scalars().all()
    scores = [r.score for r in records]
    avg = round(sum(scores) / max(1, len(scores)), 1) if scores else 0
    return {"total_records": len(records), "avg_score": avg, "pass_rate": round(sum(1 for s in scores if s >= 60) / max(1, len(scores)) * 100, 1)}

async def employee_kpi(employee_id: int) -> List[Dict[str, Any]]:
    async with session_scope() as s, bypass_tenant_filter():
        rows = (await s.execute(select(KpiRecord).where(KpiRecord.employee_id == employee_id))).scalars().all()
    return [{"id": r.id, "period": r.period, "score": r.score, "status": r.status} for r in rows]

def build_router(plugin) -> APIRouter:
    r = APIRouter(prefix=plugin.router_prefix, tags=[plugin.name])
    r.add_api_route("/rules", list_rules, methods=["GET"])
    r.add_api_route("/rules", create_rule, methods=["POST"])
    r.add_api_route("/dashboard", dashboard, methods=["GET"])
    r.add_api_route("/employee/{employee_id}", employee_kpi, methods=["GET"])
    return r
