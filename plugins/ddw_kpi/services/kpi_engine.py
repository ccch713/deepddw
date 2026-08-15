"""KPI 计算引擎"""
from __future__ import annotations



def compute_kpi(scores: list[float], weights: list[float] | None = None) -> float:
    if not scores:
        return 0.0
    if weights:
        total_w = sum(weights)
        return round(sum(s * w for s, w in zip(scores, weights)) / max(1, total_w), 2)
    return round(sum(scores) / len(scores), 2)
