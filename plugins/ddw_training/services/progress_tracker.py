"""学习进度追踪（DDW AI Hub v5.4 — 培训插件 E1）。

注意：实际数据落库由 router.py 调用 core.database.models 里的 TrainingSession/TrainingAssessment。
本服务封装业务逻辑（增量计算、总学时、雷达图聚合）。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ProgressTracker:
    def __init__(self) -> None:
        # 内存存储：生产从 DB 读
        self._sessions: List[Dict[str, Any]] = []
        self._assessments: List[Dict[str, Any]] = []

    def record_session(self, session: Dict[str, Any]) -> None:
        session.setdefault("recorded_at", datetime.utcnow().isoformat())
        self._sessions.append(session)
        logger.info("recorded training session %s user=%s", session.get("session_id"), session.get("user_id"))

    def record_assessment(self, assessment: Dict[str, Any]) -> None:
        assessment.setdefault("recorded_at", datetime.utcnow().isoformat())
        self._assessments.append(assessment)
        logger.info("recorded assessment user=%s grade=%s", assessment.get("user_id"), assessment.get("grade"))

    def user_summary(self, user_id: int) -> Dict[str, Any]:
        """个人学习汇总：总学时、章节完成度、最近 4 维评分。"""
        user_sessions = [s for s in self._sessions if s.get("user_id") == user_id]
        user_assess = [a for a in self._assessments if a.get("user_id") == user_id]
        total_seconds = sum(int(s.get("duration_sec", 0) or 0) for s in user_sessions)
        completed = [s for s in user_sessions if s.get("status") == "completed"]
        return {
            "user_id": user_id,
            "sessions_total": len(user_sessions),
            "sessions_completed": len(completed),
            "duration_minutes": round(total_seconds / 60, 1),
            "assessments_total": len(user_assess),
            "latest_score": (user_assess[-1].get("score") if user_assess else 0),
            "latest_grade": (user_assess[-1].get("grade") if user_assess else "-"),
        }

    def class_radar(self) -> Dict[str, Any]:
        """全班 4 维平均（雷达图用）。"""
        agg = defaultdict(list)
        for a in self._assessments:
            for k, v in (a.get("by_dimension") or {}).items():
                agg[k].append(v)
        return {k: round(sum(v) / max(1, len(v)), 3) for k, v in agg.items()}

    def concept_mastery(self) -> List[Dict[str, Any]]:
        """知识点掌握度（热力图用）：每个 concept 关联平均分。"""
        by_concept: Dict[str, List[float]] = defaultdict(list)
        for a in self._assessments:
            for d in a.get("details", []):
                if d.get("concept"):
                    by_concept[d["concept"]].append(d.get("score", 0))
        return [{"concept": c, "score": round(sum(v) / len(v), 3), "n": len(v)} for c, v in by_concept.items()]

    def list_sessions(self, user_id: int | None = None, limit: int = 50) -> List[Dict[str, Any]]:
        items = self._sessions
        if user_id is not None:
            items = [s for s in items if s.get("user_id") == user_id]
        return items[-limit:][::-1]


__all__ = ["ProgressTracker"]
