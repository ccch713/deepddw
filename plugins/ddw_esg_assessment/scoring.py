"""Score calculator — translated from scoring.ts.

Provides:
  - round_half_up
  - get_score_level / get_score_level_en
  - calculate_scores_by_framework
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any


def round_half_up(n: float) -> int:
    """Round a float to nearest integer using banker's half-up rule."""
    return int(Decimal(str(n)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def get_score_level(score: float) -> str:
    """Chinese level label."""
    if score >= 81:
        return "优秀"
    if score >= 61:
        return "良好"
    if score >= 41:
        return "中等"
    if score >= 21:
        return "待改进"
    return "不合格"


def get_score_level_en(score: float) -> str:
    """English level label."""
    if score >= 80:
        return "excellent"
    if score >= 60:
        return "good"
    if score >= 40:
        return "medium"
    if score >= 20:
        return "poor"
    return "fail"


def calculate_scores_by_framework(
    questions: list[dict[str, Any]],
    answers: dict[str, Any],
    theme_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Calculate theme scores, indicator scores, and total score.

    Algorithm (mirrors TS calculateScoresByFramework):
    1. Group questions by theme_id.
    2. For each question: score = (answer.value / question.max_score) * 100
    3. Theme score = average of question scores in that theme.
    4. Total score = weighted average of theme scores (equal weight if none given).
    5. Returns rounded integers for all scores.

    Parameters
    ----------
    questions : list[dict]
        Each dict must have keys: id, theme_id, max_score (default 4).
    answers : dict[str, int]
        Mapping of question_id -> selected option value (0-based int).
    theme_weights : dict[str, float] | None
        Optional per-theme weight. Equal weights used when None.

    Returns
    -------
    dict with keys: theme_scores, indicator_scores, total_score, grade, level_cn
    """
    # Group by theme
    themes: dict[str, list[dict[str, Any]]] = {}
    for q in questions:
        tid = q.get("theme_id", "unknown")
        themes.setdefault(tid, []).append(q)

    theme_scores: dict[str, float] = {}
    indicator_scores: dict[str, float] = {}

    for tid, theme_questions in themes.items():
        q_scores: list[float] = []
        for q in theme_questions:
            qid = q["id"]
            max_score = q.get("max_score", 4)
            raw_answer = answers.get(qid)
            if raw_answer is None or max_score == 0:
                continue
            val = float(raw_answer)
            score = (val / max_score) * 100.0
            indicator_scores[qid] = round_half_up(score)
            q_scores.append(score)

        if q_scores:
            theme_scores[tid] = round_half_up(sum(q_scores) / len(q_scores))
        else:
            theme_scores[tid] = 0

    # Total score: weighted or equal-weighted average
    if theme_weights:
        total = 0.0
        weight_sum = 0.0
        for tid, ts in theme_scores.items():
            w = theme_weights.get(tid, 1.0)
            total += ts * w
            weight_sum += w
        total_score = total / weight_sum if weight_sum > 0 else 0.0
    else:
        if theme_scores:
            total_score = sum(theme_scores.values()) / len(theme_scores)
        else:
            total_score = 0.0

    total_score_rounded = round_half_up(total_score)
    return {
        "theme_scores": theme_scores,
        "indicator_scores": indicator_scores,
        "total_score": total_score_rounded,
        "grade": get_score_level_en(total_score),
        "level_cn": get_score_level(total_score),
    }
