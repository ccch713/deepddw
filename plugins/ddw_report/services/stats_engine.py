"""统计计算引擎"""
from __future__ import annotations

from typing import Any, Dict, List


def compute_trends(assessments: List[Any]) -> List[Dict[str, Any]]:
    return [{"id": r.id, "score": r.overall_score, "grade": r.grade} for r in assessments]

def compute_averages(scores: List[float]) -> float:
    return round(sum(scores) / max(1, len(scores)), 2)
