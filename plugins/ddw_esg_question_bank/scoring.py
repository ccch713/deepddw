"""Score calculation engine for ESG question bank.

Translates the TypeScript scoring logic (scoring.ts / calculateScoresByFramework)
into Python with exact boundary semantics matching the original.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

# ── Score level definitions (TS SCORE_LEVELS) ────────────────────────────────

SCORE_LEVELS: dict[str, dict[str, Any]] = {
    "excellent": {"min": 80, "max": 100, "label": "优秀", "color": "#34C759"},
    "good": {"min": 60, "max": 79, "label": "良好", "color": "#007AFF"},
    "medium": {"min": 40, "max": 59, "label": "中等", "color": "#FF9500"},
    "poor": {"min": 20, "max": 39, "label": "待改进", "color": "#FF3B30"},
    "fail": {"min": 0, "max": 19, "label": "不合格", "color": "#8E8E93"},
}

SCORE_LEVELS_EN: dict[str, dict[str, Any]] = {
    "excellent": {"min": 80, "max": 100, "label": "优秀", "label_en": "Excellent", "color": "#34C759"},
    "good": {"min": 60, "max": 79, "label": "良好", "label_en": "Good", "color": "#007AFF"},
    "medium": {"min": 40, "max": 59, "label": "中等", "label_en": "Medium", "color": "#FF9500"},
    "poor": {"min": 20, "max": 39, "label": "待改进", "label_en": "Poor", "color": "#FF3B30"},
    "fail": {"min": 0, "max": 19, "label": "不合格", "label_en": "Fail", "color": "#8E8E93"},
}


def round_half_up(value: float) -> float:
    """Round using banker's half-up: 0.5 rounds away from zero.

    Uses Python's decimal module with ROUND_HALF_UP for exact match
    with the TypeScript ``Math.round()`` semantics on positive numbers.
    """
    return float(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def get_score_level(score: float) -> str:
    """Return Chinese label for score level."""
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
    """Return English code for score level."""
    if score >= 80:
        return "excellent"
    if score >= 60:
        return "good"
    if score >= 40:
        return "medium"
    if score >= 20:
        return "poor"
    return "fail"


def get_score_level_detail(score: float) -> dict[str, Any]:
    """Return full level info including label, color, and boundaries."""
    level = get_score_level_en(score)
    info = SCORE_LEVELS_EN[level]
    return {
        "code": level,
        "label": info["label"],
        "label_en": info["label_en"],
        "color": info["color"],
        "min": info["min"],
        "max": info["max"],
    }


def calculate_question_score(answer_value: int, max_score: int) -> float:
    """Calculate normalized score for a single question (0-100).

    From TS: score = (answer.value / maxScore) * 100
    """
    if max_score <= 0:
        return 0.0
    return (answer_value / max_score) * 100


def calculate_theme_score(question_scores: list[float]) -> float:
    """Calculate average score for a theme from its question scores."""
    if not question_scores:
        return 0.0
    return sum(question_scores) / len(question_scores)


def calculate_total_score(theme_scores: list[dict[str, Any]]) -> float:
    """Calculate weighted total score across themes.

    Each theme has a weight. Total = weighted average of theme scores.
    Falls back to simple average if weights don't sum to 1.
    """
    if not theme_scores:
        return 0.0

    total_weight = sum(t["weight"] for t in theme_scores)
    if total_weight == 0:
        return 0.0

    weighted_sum = sum(t["score"] * t["weight"] for t in theme_scores)
    return (weighted_sum / total_weight) * (100 / 100)  # already in 0-100


def calculate_scores_by_framework(
    framework: dict[str, Any],
    answers: dict[str, int],
) -> dict[str, Any]:
    """Full scoring pipeline matching TS calculateScoresByFramework.

    Args:
        framework: Framework dict with themes and indicators.
        answers: Mapping of question_id -> answer_value.

    Returns:
        Dict with total_score, level, theme_scores, indicator_scores.
    """
    themes = framework.get("themes", [])
    indicators = framework.get("indicators", [])

    # Build question lookup
    question_map: dict[str, dict[str, Any]] = {}
    indicator_map: dict[str, dict[str, Any]] = {}
    for ind in indicators:
        indicator_map[ind["code"]] = ind
        for q in ind.get("questions", []):
            question_map[q["id"]] = {**q, "indicator_code": ind["code"], "theme_id": ind["theme_id"]}

    # Group questions by theme
    theme_questions: dict[str, list[str]] = {}
    for theme in themes:
        tid = theme["id"]
        theme_questions[tid] = [
            qid for qid, q in question_map.items() if q.get("theme_id") == tid
        ]

    # Calculate per-question scores
    question_scores_map: dict[str, float] = {}
    for qid, answer_val in answers.items():
        q = question_map.get(qid)
        if q is None:
            continue
        max_score = q["score_range"][1] if q.get("score_range") else 5
        question_scores_map[qid] = calculate_question_score(answer_val, max_score)

    # Calculate theme scores
    theme_score_results = []
    for theme in themes:
        tid = theme["id"]
        tname = theme["name"]
        tweight = theme.get("weight", 1.0)
        qids = theme_questions.get(tid, [])
        scores = [question_scores_map[qid] for qid in qids if qid in question_scores_map]
        theme_avg = calculate_theme_score(scores) if scores else 0.0
        theme_score_results.append({
            "theme_id": tid,
            "theme_name": tname,
            "score": round_half_up(theme_avg),
            "weight": tweight,
            "question_count": len(qids),
            "answered_count": len(scores),
        })

    # Calculate indicator scores
    indicator_score_results = []
    for ind in indicators:
        ind_scores = []
        for q in ind.get("questions", []):
            if q["id"] in question_scores_map:
                ind_scores.append(question_scores_map[q["id"]])
        ind_avg = calculate_theme_score(ind_scores) if ind_scores else 0.0
        indicator_score_results.append({
            "indicator_code": ind["code"],
            "indicator_name": ind["name"],
            "theme_id": ind["theme_id"],
            "score": round_half_up(ind_avg),
            "weight": ind.get("weight", 1.0),
        })

    # Total score
    total = round_half_up(calculate_total_score(theme_score_results))
    level_en = get_score_level_en(total)
    level_zh = get_score_level(total)
    level_detail = get_score_level_detail(total)

    total_questions = len(question_map)
    answered_questions = len(answers)
    completion_rate = (answered_questions / total_questions * 100) if total_questions > 0 else 0.0

    return {
        "framework_id": framework["id"],
        "total_score": total,
        "level": level_en,
        "level_label": level_zh,
        "level_color": level_detail["color"],
        "theme_scores": theme_score_results,
        "indicator_scores": indicator_score_results,
        "total_questions": total_questions,
        "answered_questions": answered_questions,
        "completion_rate": round_half_up(completion_rate),
    }
