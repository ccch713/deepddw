"""DDW ESG Question Bank plugin — ESG assessment engine with 12 frameworks and 209+ questions.

Provides API endpoints for:
- Framework listing and detail
- Question bank retrieval with filtering
- Assessment scoring
- Score level definitions
- Framework search and recommendation
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

try:
    from .loader import (
        get_framework,
        get_question_map,
        list_frameworks,
        load_all_frameworks,
        recommend_frameworks,
        search_frameworks,
    )
    from .models import (
        AssessRequest,
        AssessResponse,
        FrameworkDetail,
        FrameworkSummary,
        HealthResponse,
        IndicatorScore,
        QuestionBankMeta,
        ScoreLevelInfo,
        SearchResult,
        ThemeScore,
    )
    from .scoring import (
        SCORE_LEVELS_EN,
        calculate_scores_by_framework,
        get_score_level_detail,
        round_half_up,
    )
except ImportError:
    from loader import (  # type: ignore[no-redef]
        get_framework,
        get_question_map,
        list_frameworks,
        load_all_frameworks,
        recommend_frameworks,
        search_frameworks,
    )
    from models import (  # type: ignore[no-redef]
        AssessRequest,
        AssessResponse,
        FrameworkDetail,
        FrameworkSummary,
        HealthResponse,
        IndicatorScore,
        QuestionBankMeta,
        ScoreLevelInfo,
        SearchResult,
        ThemeScore,
    )
    from scoring import (  # type: ignore[no-redef]
        SCORE_LEVELS_EN,
        calculate_scores_by_framework,
        get_score_level_detail,
        round_half_up,
    )

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/plugins/ddw-esg-question-bank",
    tags=["ddw-esg-question-bank"],
)

# ── Framework serialization helpers ──────────────────────────────────────────


def _framework_to_dict(fw: Any) -> dict:
    """Convert a Framework dataclass to a JSON-serializable dict."""
    return {
        "id": fw.id,
        "name": fw.name,
        "organization": fw.organization,
        "url": fw.url,
        "description": fw.description,
        "version": fw.version,
        "category": fw.category.value,
        "status": fw.status.value,
        "standard_code": fw.standard_code,
        "is_mandatory": fw.is_mandatory,
        "issuing_body": fw.issuing_body,
        "issue_date": fw.issue_date,
        "effective_date": fw.effective_date,
        "supported_sizes": [s.value for s in fw.supported_sizes],
        "category_color": fw.category_color,
        "themes": [
            {
                "id": t.id,
                "name": t.name,
                "category": t.category.value,
                "weight": t.weight,
                "description": t.description,
                "color": t.color,
            }
            for t in fw.themes
        ],
        "indicators": [
            {
                "code": ind.code,
                "name": ind.name,
                "theme_id": ind.theme_id,
                "weight": ind.weight,
                "description": ind.description,
                "questions": [
                    {
                        "id": q.id,
                        "text": q.text,
                        "type": q.type.value,
                        "options": [
                            {"value": o.value, "label": o.label, "weight": o.weight}
                            for o in q.options
                        ],
                        "required": q.required,
                        "score_range": list(q.score_range),
                        "default_score": q.default_score,
                        "help_text": q.help_text,
                        "evidence_required": q.evidence_required,
                        "display_order": q.display_order,
                        "theme_id": q.theme_id,
                        "indicator_code": q.indicator_code,
                    }
                    for q in ind.questions
                ],
                "requirements": ind.requirements,
                "suggestions": ind.suggestions,
            }
            for ind in fw.indicators
        ],
        "rating_levels": [
            {
                "code": r.code,
                "name": r.name,
                "min_score": r.min_score,
                "max_score": r.max_score,
                "description": r.description,
                "prerequisites": r.prerequisites,
            }
            for r in (fw.rating_levels or [])
        ],
    }


# ── Health check ─────────────────────────────────────────────────────────────


@router.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    frameworks = list_frameworks()
    return {
        "plugin": "ddw-esg-question-bank",
        "status": "ok",
        "frameworks_loaded": len(frameworks),
    }


# ── Frameworks ───────────────────────────────────────────────────────────────


@router.get("/frameworks")
async def list_all_frameworks(
    category: Optional[str] = Query(None, description="Filter by category"),
    status: Optional[str] = Query(None, description="Filter by status"),
) -> list[dict]:
    """List all frameworks, optionally filtered by category and/or status."""
    frameworks = list_frameworks(category=category, status=status)
    result = []
    for fw in frameworks:
        q_count = sum(len(ind.questions) for ind in fw.indicators)
        result.append({
            "id": fw.id,
            "name": fw.name,
            "organization": fw.organization,
            "description": fw.description,
            "category": fw.category.value,
            "status": fw.status.value,
            "question_count": q_count,
            "theme_count": len(fw.themes),
            "is_mandatory": fw.is_mandatory,
            "supported_sizes": [s.value for s in fw.supported_sizes],
        })
    return result


@router.get("/frameworks/{framework_id}")
async def get_framework_detail(framework_id: str) -> dict:
    """Get framework detail with themes and indicators."""
    fw = get_framework(framework_id)
    if fw is None:
        raise HTTPException(status_code=404, detail=f"Framework '{framework_id}' not found")
    return _framework_to_dict(fw)


@router.get("/frameworks/{framework_id}/questions")
async def get_framework_questions(
    framework_id: str,
    theme_id: Optional[str] = Query(None, description="Filter by theme ID"),
    indicator_code: Optional[str] = Query(None, description="Filter by indicator code"),
) -> dict:
    """Get the full question bank for a framework, with optional filtering."""
    fw = get_framework(framework_id)
    if fw is None:
        raise HTTPException(status_code=404, detail=f"Framework '{framework_id}' not found")

    questions = []
    for ind in fw.indicators:
        if indicator_code and ind.code != indicator_code:
            continue
        for q in ind.questions:
            if theme_id and q.theme_id != theme_id:
                continue
            questions.append({
                "id": q.id,
                "text": q.text,
                "type": q.type.value,
                "options": [
                    {"value": o.value, "label": o.label, "weight": o.weight}
                    for o in q.options
                ],
                "required": q.required,
                "score_range": list(q.score_range),
                "theme_id": q.theme_id,
                "indicator_code": q.indicator_code,
                "help_text": q.help_text,
                "evidence_required": q.evidence_required,
                "display_order": q.display_order,
            })

    return {
        "framework_id": framework_id,
        "total": len(questions),
        "questions": questions,
    }


@router.get("/frameworks/{framework_id}/meta")
async def get_question_bank_meta(framework_id: str) -> dict:
    """Get question bank metadata for a framework."""
    fw = get_framework(framework_id)
    if fw is None:
        raise HTTPException(status_code=404, detail=f"Framework '{framework_id}' not found")

    themes = [
        {
            "id": t.id,
            "name": t.name,
            "category": t.category.value,
            "weight": t.weight,
            "question_count": sum(
                len(ind.questions) for ind in fw.indicators if ind.theme_id == t.id
            ),
        }
        for t in fw.themes
    ]

    indicators = [
        {
            "code": ind.code,
            "name": ind.name,
            "theme_id": ind.theme_id,
            "weight": ind.weight,
            "question_count": len(ind.questions),
        }
        for ind in fw.indicators
    ]

    total_questions = sum(len(ind.questions) for ind in fw.indicators)

    return {
        "framework_id": framework_id,
        "framework_name": fw.name,
        "total_questions": total_questions,
        "total_indicators": len(fw.indicators),
        "total_themes": len(fw.themes),
        "themes": themes,
        "indicators": indicators,
    }


# ── Assessment ───────────────────────────────────────────────────────────────


@router.post("/assess")
async def assess(request: AssessRequest) -> dict:
    """Submit answers and get scores for a framework."""
    fw = get_framework(request.framework_id)
    if fw is None:
        raise HTTPException(status_code=404, detail=f"Framework '{request.framework_id}' not found")

    fw_dict = _framework_to_dict(fw)
    answers = {a.question_id: a.value for a in request.answers}

    result = calculate_scores_by_framework(fw_dict, answers)
    return result


@router.get("/assess/levels")
async def get_assess_levels() -> list[dict]:
    """Get score level definitions."""
    levels = []
    for code, info in SCORE_LEVELS_EN.items():
        levels.append({
            "code": code,
            "label": info["label"],
            "label_en": info["label_en"],
            "min": info["min"],
            "max": info["max"],
            "color": info["color"],
            "description": {
                "excellent": "ESG管理成熟，达到行业领先水平",
                "good": "ESG管理规范，高于行业平均水平",
                "medium": "ESG管理基本合规，有改进空间",
                "poor": "ESG管理薄弱，需系统性提升",
                "fail": "ESG管理严重缺失，需立即整改",
            }.get(code, ""),
        })
    return levels


# ── Search & Recommendation ──────────────────────────────────────────────────


@router.get("/search")
async def search(q: str = Query(..., description="Search keyword")) -> list[dict]:
    """Search frameworks by keyword."""
    frameworks = search_frameworks(q)
    results = []
    for fw in frameworks:
        q_count = sum(len(ind.questions) for ind in fw.indicators)
        results.append({
            "id": fw.id,
            "name": fw.name,
            "organization": fw.organization,
            "description": fw.description,
            "relevance_score": 1.0,
        })
    return results


@router.get("/recommend")
async def recommend(
    company_size: str = Query(..., description="Company size: micro/small/medium/large/enterprise"),
) -> list[dict]:
    """Recommend frameworks suitable for a given company size."""
    frameworks = recommend_frameworks(company_size)
    results = []
    for fw in frameworks:
        q_count = sum(len(ind.questions) for ind in fw.indicators)
        results.append({
            "id": fw.id,
            "name": fw.name,
            "organization": fw.organization,
            "description": fw.description,
            "question_count": q_count,
            "category": fw.category.value,
            "status": fw.status.value,
        })
    return results


# ── Plugin registration ──────────────────────────────────────────────────────


TOOL_ANNOTATIONS: dict[str, dict] = {
    "list_frameworks": {'readOnly': True},
    "get_framework_detail": {'readOnly': True},
    "get_framework_questions": {'readOnly': True},
    "get_question_bank_meta": {'readOnly': True},
    "search": {'readOnly': True},
    "recommend": {'readOnly': True},
    "get_assess_levels": {'readOnly': True},
    "assess": {'readOnly': False},
}

def register(app: Any) -> None:
    """Register this plugin's router with the FastAPI application."""
    # Load framework data at startup
    load_all_frameworks()
    app.include_router(router)
    logger.info("ddw-esg-question-bank plugin registered")
