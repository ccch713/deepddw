"""DDW 培训插件 API 路由（DDW AI Hub v5.4 — 培训插件 E1，对接 DB）。

端点：
- ``GET    /api/v1/plugins/ddw-training/courses``
- ``POST   /api/v1/plugins/ddw-training/sessions/start``  写 training_sessions
- ``POST   /api/v1/plugins/ddw-training/sessions/chat``   写 training_sessions（完成时）
- ``POST   /api/v1/plugins/ddw-training/quiz/generate``
- ``POST   /api/v1/plugins/ddw-training/quiz/grade``       写 training_assessments
- ``GET    /api/v1/plugins/ddw-training/progress/{user_id}``
- ``GET    /api/v1/plugins/ddw-training/class/radar``
- ``GET    /api/v1/plugins/ddw-training/class/mastery``
- ``GET    /api/v1/plugins/ddw-training/coursewares``
- ``GET    /api/v1/plugins/ddw-training/pedagogy/moves``
- ``GET    /api/v1/plugins/ddw-training/pedagogy/vignettes``

内存会话（plugin._active_sessions）仍用于实时对话；持久化数据走 DB。
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from core.database.models import TrainingAssessment, TrainingSession
from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas（模块级，避开 Pydantic forward-ref 问题）
# ---------------------------------------------------------------------------


class StartSessionReq(BaseModel):
    user_id: int
    tenant_id: int = 1
    subject: str = "physics"
    course_id: str = "default"


class ChatReq(BaseModel):
    session_id: str
    message: str


class QuizReq(BaseModel):
    subject: str = "physics"
    n: int = 5


class GradeReq(BaseModel):
    question: Dict[str, Any]
    student_answer: str
    user_id: int
    session_id: Optional[str] = None
    subject: str = "physics"


# ---------------------------------------------------------------------------
# 课程
# ---------------------------------------------------------------------------


async def list_courses() -> List[Dict[str, Any]]:
    return [
        {"id": "physics-g9", "subject": "physics", "display_name": "初三物理", "grade": 9},
        {"id": "chemistry-g9", "subject": "chemistry", "display_name": "初三化学", "grade": 9},
    ]


# ---------------------------------------------------------------------------
# 会话
# ---------------------------------------------------------------------------


async def start_session(req: StartSessionReq, plugin) -> Dict[str, Any]:
    """创建培训会话：先写 DB 拿 db_id，再在内存中创建 SessionState。"""
    sid = uuid.uuid4().hex[:16]
    async with session_scope() as session, bypass_tenant_filter():
        db_sess = TrainingSession(
            tenant_id=req.tenant_id,
            user_id=req.user_id,
            session_uuid=sid,
            course_id=req.course_id,
            subject=req.subject,
            status="active",
        )
        session.add(db_sess)
        await session.commit()
        await session.refresh(db_sess)
        db_id = db_sess.id
    plugin.start_training_session(
        user_id=req.user_id,
        tenant_id=req.tenant_id,
        subject=req.subject,
        course_id=req.course_id,
        session_uuid=sid,
    )
    return {
        "session_id": sid,
        "db_id": db_id,
        "subject": req.subject,
        "course_id": req.course_id,
    }


async def chat(req: ChatReq, plugin) -> Dict[str, Any]:
    """苏格拉底对话；会话完成时回写 training_sessions。"""
    result = await plugin.chat(req.session_id, req.message)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    if result.get("completed"):
        mem = plugin.get_session(req.session_id)
        moves = ",".join(str(m) for m in (mem.moves_completed if mem else []))
        scores = mem.scores if mem else {}
        async with session_scope() as session, bypass_tenant_filter():
            row = (
                await session.execute(
                    select(TrainingSession).where(TrainingSession.session_uuid == req.session_id)
                )
            ).scalar_one_or_none()
            if row is not None:
                row.status = "completed"
                row.ended_at = datetime.utcnow()
                row.moves_completed = moves
                row.final_scores = json.dumps(scores, ensure_ascii=False)
                if row.started_at:
                    row.duration_sec = int((row.ended_at - row.started_at).total_seconds())
                await session.commit()
        plugin.close_session(req.session_id)
    return result


# ---------------------------------------------------------------------------
# 测验
# ---------------------------------------------------------------------------


async def generate_quiz(req: QuizReq, plugin) -> Dict[str, Any]:
    qs = plugin.assessment.generate_quiz(req.subject, req.n)
    return {"subject": req.subject, "questions": qs}


async def grade(req: GradeReq, plugin) -> Dict[str, Any]:
    """评分 → 写 training_assessments 表 → 4 维聚合 → 评级。"""
    single = plugin.assessment.grade(req.question, req.student_answer)
    agg = plugin.assessment.overall_grade([single])
    async with session_scope() as session, bypass_tenant_filter():
        sess_db_id: Optional[int] = None
        if req.session_id:
            row = (
                await session.execute(
                    select(TrainingSession).where(TrainingSession.session_uuid == req.session_id)
                )
            ).scalar_one_or_none()
            if row is not None:
                sess_db_id = row.id
        ta = TrainingAssessment(
            tenant_id=1,  # 简化：评分场景下从 token 取
            user_id=req.user_id,
            session_id=sess_db_id,
            subject=req.subject,
            overall_score=int(agg["score"] * 100),
            conceptual_clarity=int(agg["by_dimension"]["conceptual_clarity"] * 100),
            reasoning_depth=int(agg["by_dimension"]["reasoning_depth"] * 100),
            engagement_quality=int(agg["by_dimension"]["engagement_quality"] * 100),
            pedagogical_alignment=int(agg["by_dimension"]["pedagogical_alignment"] * 100),
            grade=agg["grade"],
            details_json=json.dumps(
                {
                    "question": req.question,
                    "student_answer": req.student_answer,
                    "single_result": single,
                },
                ensure_ascii=False,
            ),
        )
        session.add(ta)
        await session.commit()
        await session.refresh(ta)
        assessment_id = ta.id
    return {
        "assessment_id": assessment_id,
        "score": single["score"],
        "correct": single["correct"],
        "feedback": single["feedback"],
        "overall": agg,
    }


# ---------------------------------------------------------------------------
# 课件 / 教学法配置
# ---------------------------------------------------------------------------


async def list_coursewares(course_id: Optional[str], plugin) -> List[Dict[str, Any]]:
    items = plugin.courseware.list_by_course(course_id) if course_id else plugin.courseware.list_all()
    return [plugin.courseware.to_dict(c) for c in items]


async def moves(plugin) -> List[Dict[str, Any]]:
    return plugin.socratic._moves


async def vignettes(plugin) -> List[Dict[str, Any]]:
    return plugin.socratic._vignettes


# ---------------------------------------------------------------------------
# 进度（从 DB）
# ---------------------------------------------------------------------------


async def user_progress(user_id: int) -> Dict[str, Any]:
    async with session_scope() as session, bypass_tenant_filter():
        sessions = (
            await session.execute(
                select(TrainingSession).where(TrainingSession.user_id == user_id).order_by(TrainingSession.id)
            )
        ).scalars().all()
        assessments = (
            await session.execute(
                select(TrainingAssessment).where(TrainingAssessment.user_id == user_id).order_by(TrainingAssessment.id)
            )
        ).scalars().all()
    total_sec = sum(s.duration_sec or 0 for s in sessions)
    completed = [s for s in sessions if s.status == "completed"]
    latest = assessments[-1] if assessments else None
    return {
        "user_id": user_id,
        "sessions_total": len(sessions),
        "sessions_completed": len(completed),
        "duration_minutes": round(total_sec / 60, 1),
        "assessments_total": len(assessments),
        "latest_score": latest.overall_score if latest else 0,
        "latest_grade": latest.grade if latest else "-",
        "latest_subject": latest.subject if latest else None,
    }


async def class_radar() -> Dict[str, Any]:
    async with session_scope() as session, bypass_tenant_filter():
        rows = (await session.execute(select(TrainingAssessment))).scalars().all()
    agg: Dict[str, List[float]] = {
        "conceptual_clarity": [],
        "reasoning_depth": [],
        "engagement_quality": [],
        "pedagogical_alignment": [],
    }
    for r in rows:
        for k in agg:
            v = getattr(r, k, None)
            if v is not None:
                agg[k].append(float(v) / 100.0)
    return {k: round(sum(v) / max(1, len(v)), 3) for k, v in agg.items()}


async def class_mastery() -> List[Dict[str, Any]]:
    async with session_scope() as session, bypass_tenant_filter():
        rows = (await session.execute(select(TrainingAssessment))).scalars().all()
    bucket: Dict[str, List[float]] = {}
    for r in rows:
        try:
            details = json.loads(r.details_json or "{}")
        except json.JSONDecodeError:
            continue
        q = details.get("question") or {}
        concept = q.get("concept")
        single = details.get("single_result") or {}
        score = single.get("score")
        if concept and isinstance(score, (int, float)):
            bucket.setdefault(concept, []).append(float(score))
    return [
        {"concept": c, "score": round(sum(v) / len(v), 3), "n": len(v)}
        for c, v in bucket.items()
    ]


# ---------------------------------------------------------------------------
# Router 工厂
# ---------------------------------------------------------------------------


def build_router(plugin) -> APIRouter:
    """构造培训插件 router。prefix 直接带 /api/v1/plugins/{plugin.name}。"""
    router = APIRouter(prefix=f"/api/v1/plugins/{plugin.name}", tags=[plugin.name])

    # 全部用 async def 包装（不能 lambda，会丢 await）
    async def _moves():
        return await moves(plugin)
    async def _vignettes():
        return await vignettes(plugin)
    async def _user_progress(user_id: int):
        return await user_progress(user_id)
    async def _start_session(req: StartSessionReq):
        return await start_session(req, plugin)
    async def _chat(req: ChatReq):
        return await chat(req, plugin)
    async def _generate_quiz(req: QuizReq):
        return await generate_quiz(req, plugin)
    async def _grade(req: GradeReq):
        return await grade(req, plugin)
    async def _list_coursewares(course_id: Optional[str] = None):
        return await list_coursewares(course_id, plugin)

    router.add_api_route("/courses", list_courses, methods=["GET"])
    router.add_api_route("/pedagogy/moves", _moves, methods=["GET"])
    router.add_api_route("/pedagogy/vignettes", _vignettes, methods=["GET"])
    router.add_api_route("/progress/{user_id}", _user_progress, methods=["GET"])
    router.add_api_route("/class/radar", class_radar, methods=["GET"])
    router.add_api_route("/class/mastery", class_mastery, methods=["GET"])
    router.add_api_route("/sessions/start", _start_session, methods=["POST"])
    router.add_api_route("/sessions/chat", _chat, methods=["POST"])
    router.add_api_route("/quiz/generate", _generate_quiz, methods=["POST"])
    router.add_api_route("/quiz/grade", _grade, methods=["POST"])
    router.add_api_route("/coursewares", _list_coursewares, methods=["GET"])

    
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw_training", "version": "0.1.0", "status": "ok"}

    return router


__all__ = ["build_router"]
