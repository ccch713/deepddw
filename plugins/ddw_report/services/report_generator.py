"""报表生成器"""
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import select

from core.database.models import TrainingAssessment, TrainingSession
from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter


async def generate_user_report(user_id: int) -> Dict[str, Any]:
    async with session_scope() as session, bypass_tenant_filter():
        sessions = (await session.execute(select(TrainingSession).where(TrainingSession.user_id == user_id))).scalars().all()
        assessments = (await session.execute(select(TrainingAssessment).where(TrainingAssessment.user_id == user_id))).scalars().all()
    return {"user_id": user_id, "sessions": len(sessions), "assessments": len(assessments)}
