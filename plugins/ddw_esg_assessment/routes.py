"""API routes for DDW ESG Assessment plugin.

10 endpoints:
  1. GET  /frameworks                              — list available frameworks
  2. POST /assessments                            — create assessment session
  3. POST /assessments/{id}/answers               — submit answer
  4. POST /assessments/{id}/next-question         — get next question (skip logic)
  5. POST /assessments/{id}/calculate             — calculate final scores
  6. GET  /assessments                            — list user's assessments
  7. GET  /assessments/{id}                       — get assessment detail
  8. DELETE /assessments/{id}                     — delete assessment
  9. GET  /question-bank/meta                     — question bank metadata
  10. GET /health                                 — health check
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

try:
    from .benchmark import calculate_all_benchmarks
    from .models import (
        AnswerRequest,
        AssessmentResponse,
        CalculateResponse,
        CreateAssessmentRequest,
        NextQuestionResponse,
        QuestionBankMeta,
        SkipResult,
        ThemeMeta,
        get_store,
    )
    from .scoring import calculate_scores_by_framework
    from .skip_engine import compute_visibility, evaluate_skip_rules
except ImportError:
    from benchmark import calculate_all_benchmarks  # type: ignore[no-redef]
    from models import (  # type: ignore[no-redef]
        AnswerRequest,
        AssessmentResponse,
        CalculateResponse,
        CreateAssessmentRequest,
        NextQuestionResponse,
        QuestionBankMeta,
        SkipResult,
        ThemeMeta,
        get_store,
    )
    from scoring import calculate_scores_by_framework  # type: ignore[no-redef]
    from skip_engine import (  # type: ignore[no-redef]
        compute_visibility,
        evaluate_skip_rules,
    )

router = APIRouter()


# ---------------------------------------------------------------------------
# Question bank — embedded sample data
# ---------------------------------------------------------------------------

_QUESTION_BANK: list[dict[str, Any]] = [
    # --- Environmental (E) ---
    {"id": "E1", "theme_id": "E", "text": "是否建立了环境管理体系？", "text_en": "Has an environmental management system been established?", "max_score": 4, "dimension": "E", "options": [
        {"value": 0, "label": "无", "label_en": "None"}, {"value": 1, "label": "初步", "label_en": "Initial"}, {"value": 2, "label": "进行中", "label_en": "In progress"}, {"value": 3, "label": "已建立", "label_en": "Established"}, {"value": 4, "label": "认证通过", "label_en": "Certified"},
    ], "skip_rules": []},
    {"id": "E2", "theme_id": "E", "text": "碳排放是否达标？", "text_en": "Are carbon emissions compliant?", "max_score": 4, "dimension": "E", "options": [
        {"value": 0, "label": "无数据", "label_en": "No data"}, {"value": 1, "label": "超标", "label_en": "Over limit"}, {"value": 2, "label": "接近", "label_en": "Near limit"}, {"value": 3, "label": "达标", "label_en": "Compliant"}, {"value": 4, "label": "远低于", "label_en": "Well below"},
    ], "skip_rules": []},
    {"id": "E3", "theme_id": "E", "text": "废物管理是否规范？", "text_en": "Is waste management standardized?", "max_score": 4, "dimension": "E", "options": [
        {"value": 0, "label": "无管理", "label_en": "None"}, {"value": 1, "label": "初级", "label_en": "Basic"}, {"value": 2, "label": "中等", "label_en": "Moderate"}, {"value": 3, "label": "良好", "label_en": "Good"}, {"value": 4, "label": "优秀", "label_en": "Excellent"},
    ], "skip_rules": []},
    {"id": "E4", "theme_id": "E", "text": "水资源使用效率如何？", "text_en": "How efficient is water usage?", "max_score": 4, "dimension": "E", "options": [
        {"value": 0, "label": "无管理", "label_en": "None"}, {"value": 1, "label": "低效", "label_en": "Inefficient"}, {"value": 2, "label": "一般", "label_en": "Average"}, {"value": 3, "label": "高效", "label_en": "Efficient"}, {"value": 4, "label": "领先", "label_en": "Leading"},
    ], "skip_rules": []},
    # --- Social (S) ---
    {"id": "S1", "theme_id": "S", "text": "员工安全培训是否到位？", "text_en": "Is employee safety training adequate?", "max_score": 4, "dimension": "S", "options": [
        {"value": 0, "label": "无", "label_en": "None"}, {"value": 1, "label": "少量", "label_en": "Minimal"}, {"value": 2, "label": "部分", "label_en": "Partial"}, {"value": 3, "label": "全面", "label_en": "Comprehensive"}, {"value": 4, "label": "领先", "label_en": "Leading"},
    ], "skip_rules": []},
    {"id": "S2", "theme_id": "S", "text": "劳工权益保障如何？", "text_en": "How are labor rights protected?", "max_score": 4, "dimension": "S", "options": [
        {"value": 0, "label": "无保障", "label_en": "None"}, {"value": 1, "label": "基础", "label_en": "Basic"}, {"value": 2, "label": "中等", "label_en": "Moderate"}, {"value": 3, "label": "良好", "label_en": "Good"}, {"value": 4, "label": "优秀", "label_en": "Excellent"},
    ], "skip_rules": []},
    {"id": "S3", "theme_id": "S", "text": "供应链管理是否包含ESG？", "text_en": "Does supply chain management include ESG?", "max_score": 4, "dimension": "S", "options": [
        {"value": 0, "label": "无", "label_en": "None"}, {"value": 1, "label": "初步", "label_en": "Initial"}, {"value": 2, "label": "进行中", "label_en": "In progress"}, {"value": 3, "label": "已建立", "label_en": "Established"}, {"value": 4, "label": "完善", "label_en": "Mature"},
    ], "skip_rules": [
        {"type": "conditional_show", "condition": {"operator": ">=", "target": 3}, "target": None}
    ]},
    # --- Governance (G) ---
    {"id": "G1", "theme_id": "G", "text": "董事会ESG监督机制是否建立？", "text_en": "Has the board established ESG oversight?", "max_score": 4, "dimension": "G", "options": [
        {"value": 0, "label": "无", "label_en": "None"}, {"value": 1, "label": "初步", "label_en": "Initial"}, {"value": 2, "label": "进行中", "label_en": "In progress"}, {"value": 3, "label": "已建立", "label_en": "Established"}, {"value": 4, "label": "完善", "label_en": "Mature"},
    ], "skip_rules": []},
    {"id": "G2", "theme_id": "G", "text": "信息披露透明度如何？", "text_en": "How transparent is information disclosure?", "max_score": 4, "dimension": "G", "options": [
        {"value": 0, "label": "无披露", "label_en": "None"}, {"value": 1, "label": "最低要求", "label_en": "Minimum"}, {"value": 2, "label": "部分披露", "label_en": "Partial"}, {"value": 3, "label": "全面披露", "label_en": "Comprehensive"}, {"value": 4, "label": "领先实践", "label_en": "Leading"},
    ], "skip_rules": []},
    {"id": "G3", "theme_id": "G", "text": "反腐败政策执行情况？", "text_en": "Anti-corruption policy implementation?", "max_score": 4, "dimension": "G", "options": [
        {"value": 0, "label": "无", "label_en": "None"}, {"value": 1, "label": "有政策", "label_en": "Policy exists"}, {"value": 2, "label": "部分执行", "label_en": "Partial"}, {"value": 3, "label": "全面执行", "label_en": "Full"}, {"value": 4, "label": "审计通过", "label_en": "Audited"},
    ], "skip_rules": []},
]

_THEME_DEFINITIONS: list[dict[str, Any]] = [
    {"id": "E", "name": "环境 (Environmental)", "weight": 1.0},
    {"id": "S", "name": "社会 (Social)", "weight": 1.0},
    {"id": "G", "name": "治理 (Governance)", "weight": 1.0},
]

_FRAMEWORKS: list[dict[str, Any]] = [
    {"id": "ecovadis", "name": "EcoVadis", "name_en": "EcoVadis Rating"},
    {"id": "cdp", "name": "CDP", "name_en": "Carbon Disclosure Project"},
    {"id": "msci", "name": "MSCI", "name_en": "MSCI ESG Rating"},
    {"id": "sp_csa", "name": "S&P CSA", "name_en": "S&P Global CSA / DJSI"},
    {"id": "csi_esg", "name": "中证ESG", "name_en": "CSI ESG Rating"},
    {"id": "internal", "name": "内部评级", "name_en": "Internal Rating"},
]


def _get_questions() -> list[dict[str, Any]]:
    return _QUESTION_BANK


def _get_themes() -> list[dict[str, Any]]:
    return _THEME_DEFINITIONS


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "plugin": "ddw-esg-assessment"}


@router.get("/frameworks")
def list_frameworks() -> list[dict[str, str]]:
    return _FRAMEWORKS


@router.post("/assessments", response_model=AssessmentResponse)
def create_assessment(req: CreateAssessmentRequest) -> dict[str, Any]:
    store = get_store()
    assessment_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "id": assessment_id,
        "user_id": req.user_id,
        "framework_id": req.framework_id,
        "company_name": req.company_name,
        "company_size": req.company_size,
        "industry": req.industry,
        "status": "in_progress",
        "answers": {},
        "theme_scores": {},
        "indicator_scores": {},
        "total_score": None,
        "grade": None,
        "benchmark_results": {},
        "created_at": now,
        "updated_at": now,
    }
    store[assessment_id] = record
    return record


@router.post("/assessments/{assessment_id}/answers", response_model=AssessmentResponse)
def submit_answer(assessment_id: str, req: AnswerRequest) -> dict[str, Any]:
    store = get_store()
    record = store.get(assessment_id)
    if not record:
        raise HTTPException(status_code=404, detail="Assessment not found")

    record["answers"][req.question_id] = req.value
    record["updated_at"] = datetime.now(timezone.utc).isoformat()
    return record


@router.post("/assessments/{assessment_id}/next-question", response_model=NextQuestionResponse)
def next_question(assessment_id: str) -> dict[str, Any]:
    store = get_store()
    record = store.get(assessment_id)
    if not record:
        raise HTTPException(status_code=404, detail="Assessment not found")

    questions = _get_questions()
    answers = record.get("answers", {})

    # Use skip engine to compute visible questions
    visibility = compute_visibility(questions, answers)
    visible_questions = visibility["visible_questions"]
    skipped_ids = visibility["skipped_ids"]

    # Find the next unanswered visible question
    for q in visible_questions:
        qid = q["id"]
        if qid not in answers:
            # Evaluate skip rules for this question
            skip_result = evaluate_skip_rules(q, answers)
            return {
                "question": q,
                "skip_result": skip_result,
                "is_complete": False,
            }

    # All visible questions answered
    return {
        "question": None,
        "skip_result": SkipResult(skipped_ids=skipped_ids, has_skip=bool(skipped_ids)),
        "is_complete": True,
    }


@router.post("/assessments/{assessment_id}/calculate", response_model=CalculateResponse)
def calculate_scores(assessment_id: str) -> dict[str, Any]:
    store = get_store()
    record = store.get(assessment_id)
    if not record:
        raise HTTPException(status_code=404, detail="Assessment not found")

    questions = _get_questions()
    answers = record.get("answers", {})

    result = calculate_scores_by_framework(questions, answers)

    # Calculate benchmarks
    benchmark_results = calculate_all_benchmarks(
        total_score=result["total_score"],
        theme_scores=result["theme_scores"],
    )

    # Update record
    record["theme_scores"] = result["theme_scores"]
    record["indicator_scores"] = result["indicator_scores"]
    record["total_score"] = result["total_score"]
    record["grade"] = result["grade"]
    record["benchmark_results"] = benchmark_results
    record["status"] = "completed"
    record["updated_at"] = datetime.now(timezone.utc).isoformat()

    return {
        "theme_scores": result["theme_scores"],
        "indicator_scores": result["indicator_scores"],
        "total_score": result["total_score"],
        "grade": result["grade"],
        "level_cn": result["level_cn"],
        "benchmark_results": benchmark_results,
    }


@router.get("/assessments")
def list_assessments(user_id: str = Query(...)) -> list[dict[str, Any]]:
    store = get_store()
    return [r for r in store.values() if r.get("user_id") == user_id]


@router.get("/assessments/{assessment_id}", response_model=AssessmentResponse)
def get_assessment(assessment_id: str) -> dict[str, Any]:
    store = get_store()
    record = store.get(assessment_id)
    if not record:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return record


@router.delete("/assessments/{assessment_id}")
def delete_assessment(assessment_id: str) -> dict[str, str]:
    store = get_store()
    if assessment_id not in store:
        raise HTTPException(status_code=404, detail="Assessment not found")
    del store[assessment_id]
    return {"status": "deleted", "id": assessment_id}


@router.get("/question-bank/meta", response_model=QuestionBankMeta)
def question_bank_meta() -> dict[str, Any]:
    questions = _get_questions()
    themes_raw = _get_themes()

    themes = []
    for t in themes_raw:
        count = sum(1 for q in questions if q["theme_id"] == t["id"])
        themes.append(ThemeMeta(id=t["id"], name=t["name"], weight=t["weight"], question_count=count))

    dimensions = sorted(set(q.get("dimension", "") for q in questions if q.get("dimension")))

    return {
        "total_questions": len(questions),
        "themes": [t.model_dump() for t in themes],
        "dimensions": dimensions,
    }
