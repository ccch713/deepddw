"""DDW 学习报表 API 路由"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter
from sqlalchemy import func, select

from core.database.models import TrainingAssessment, TrainingSession
from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

logger = logging.getLogger(__name__)

async def user_summary(user_id: int) -> Dict[str, Any]:
    async with session_scope() as session, bypass_tenant_filter():
        sessions = (await session.execute(
            select(TrainingSession).where(TrainingSession.user_id == user_id)
        )).scalars().all()
        assessments = (await session.execute(
            select(TrainingAssessment).where(TrainingAssessment.user_id == user_id)
        )).scalars().all()
    total_sec = sum(s.duration_sec or 0 for s in sessions)
    completed = [s for s in sessions if s.status == "completed"]
    latest = assessments[-1] if assessments else None
    return {
        "user_id": user_id, "sessions_total": len(sessions),
        "sessions_completed": len(completed),
        "duration_minutes": round(total_sec / 60, 1),
        "assessments_total": len(assessments),
        "latest_score": latest.overall_score if latest else 0,
        "latest_grade": latest.grade if latest else "-",
    }

async def user_pdf(user_id: int) -> Dict[str, Any]:
    """PDF 导出（占位：返回报告数据，生产用 reportlab）"""
    data = await user_summary(user_id)
    return {"user_id": user_id, "format": "pdf", "data": data, "download_url": f"/reports/{user_id}.pdf"}

async def class_overview() -> Dict[str, Any]:
    async with session_scope() as session, bypass_tenant_filter():
        total = (await session.execute(select(func.count(TrainingSession.id)))).scalar() or 0
        completed = (await session.execute(
            select(func.count(TrainingSession.id)).where(TrainingSession.status == "completed")
        )).scalar() or 0
        avg_score = (await session.execute(
            select(func.avg(TrainingAssessment.overall_score))
        )).scalar() or 0
    return {"total_sessions": total, "completed": completed, "avg_score": round(float(avg_score), 1)}

async def user_trends(user_id: int) -> Dict[str, Any]:
    async with session_scope() as session, bypass_tenant_filter():
        rows = (await session.execute(
            select(TrainingAssessment).where(TrainingAssessment.user_id == user_id).order_by(TrainingAssessment.id)
        )).scalars().all()
    return {"user_id": user_id, "trends": [{"id": r.id, "score": r.overall_score, "grade": r.grade, "subject": r.subject} for r in rows]}

def build_router(plugin) -> APIRouter:
    router = APIRouter(prefix=plugin.router_prefix, tags=[plugin.name])
    router.add_api_route("/user/{user_id}", user_summary, methods=["GET"])
    router.add_api_route("/user/{user_id}/pdf", user_pdf, methods=["GET"])
    router.add_api_route("/class/overview", class_overview, methods=["GET"])
    router.add_api_route("/trends/{user_id}", user_trends, methods=["GET"])
    return router
