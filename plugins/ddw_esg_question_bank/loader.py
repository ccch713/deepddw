"""JSON loader and in-memory cache for ESG framework data.

Loads framework definitions from ``data/frameworks/*.json`` at startup,
converts them to domain dataclasses, and provides lookup functions.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

try:
    from .models import (
        CompanySize,
        Framework,
        FrameworkStatus,
        Indicator,
        Question,
        QuestionOption,
        QuestionType,
        RatingLevel,
        StandardCategory,
        Theme,
        ThemeCategory,
    )
except ImportError:
    from models import (  # type: ignore[no-redef]
        CompanySize,
        Framework,
        FrameworkStatus,
        Indicator,
        Question,
        QuestionOption,
        QuestionType,
        RatingLevel,
        StandardCategory,
        Theme,
        ThemeCategory,
    )

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent / "data" / "frameworks"

# In-memory cache: framework_id -> Framework
_frameworks: dict[str, Framework] = {}
_loaded = False


def _parse_question(raw: dict[str, Any], theme_id: str, indicator_code: str) -> Question:
    """Parse a raw JSON question dict into a Question dataclass."""
    options = [
        QuestionOption(
            value=o["value"],
            label=o["label"],
            weight=o.get("weight"),
        )
        for o in raw.get("options", [])
    ]
    score_range = tuple(raw.get("score_range", [1, 5]))  # type: ignore[assignment]
    return Question(
        id=raw["id"],
        text=raw["text"],
        type=QuestionType(raw.get("type", "likert5")),
        options=options,
        required=raw.get("required", True),
        score_range=score_range,  # type: ignore[arg-type]
        default_score=raw.get("default_score"),
        help_text=raw.get("help_text"),
        evidence_required=raw.get("evidence_required"),
        display_order=raw.get("display_order"),
        theme_id=theme_id,
        indicator_code=indicator_code,
        skip_rules=raw.get("skip_rules"),
        show_condition=raw.get("show_condition"),
    )


def _parse_indicator(raw: dict[str, Any], theme_id: str) -> Indicator:
    """Parse a raw JSON indicator dict into an Indicator dataclass."""
    questions = [_parse_question(q, theme_id, raw["code"]) for q in raw.get("questions", [])]
    return Indicator(
        code=raw["code"],
        name=raw["name"],
        theme_id=theme_id,
        weight=raw.get("weight", 1.0),
        description=raw.get("description"),
        questions=questions,
        requirements=raw.get("requirements", []),
        suggestions=raw.get("suggestions", []),
    )


def _parse_theme(raw: dict[str, Any]) -> Theme:
    """Parse a raw JSON theme dict into a Theme dataclass."""
    return Theme(
        id=raw["id"],
        name=raw["name"],
        category=ThemeCategory(raw.get("category", "environment")),
        weight=raw.get("weight", 1.0),
        description=raw.get("description"),
        color=raw.get("color"),
    )


def _parse_rating_level(raw: dict[str, Any]) -> RatingLevel:
    """Parse a raw JSON rating level dict into a RatingLevel dataclass."""
    return RatingLevel(
        code=raw["code"],
        name=raw["name"],
        min_score=raw["min_score"],
        max_score=raw["max_score"],
        description=raw.get("description", ""),
        prerequisites=raw.get("prerequisites"),
    )


def _parse_framework(raw: dict[str, Any]) -> Framework:
    """Parse a raw JSON framework dict into a Framework dataclass."""
    themes = [_parse_theme(t) for t in raw.get("themes", [])]

    # Build theme_id -> theme lookup for indicators
    theme_map = {t.id: t for t in themes}

    # Indicators reference theme_id; parse them
    indicators = []
    for ind_raw in raw.get("indicators", []):
        tid = ind_raw.get("theme_id", "")
        indicators.append(_parse_indicator(ind_raw, tid))

    rating_levels = None
    if raw.get("rating_levels"):
        rating_levels = [_parse_rating_level(r) for r in raw["rating_levels"]]

    return Framework(
        id=raw["id"],
        name=raw["name"],
        organization=raw.get("organization", ""),
        url=raw.get("url", ""),
        description=raw.get("description", ""),
        supported_sizes=[CompanySize(s) for s in raw.get("supported_sizes", ["small", "medium", "large"])],
        themes=themes,
        indicators=indicators,
        version=raw.get("version", "1.0.0"),
        category=StandardCategory(raw.get("category", "national")),
        status=FrameworkStatus(raw.get("status", "available")),
        standard_code=raw.get("standard_code"),
        is_mandatory=raw.get("is_mandatory", False),
        issuing_body=raw.get("issuing_body"),
        issue_date=raw.get("issue_date"),
        effective_date=raw.get("effective_date"),
        category_color=raw.get("category_color"),
        rating_levels=rating_levels,
    )


def load_all_frameworks() -> dict[str, Framework]:
    """Load all framework JSON files from data/frameworks/.

    Returns dict of framework_id -> Framework. Cached after first call.
    """
    global _loaded
    if _loaded and _frameworks:
        return _frameworks

    _frameworks.clear()

    if not _DATA_DIR.exists():
        logger.warning("Framework data directory not found: %s", _DATA_DIR)
        return _frameworks

    for json_file in sorted(_DATA_DIR.glob("*.json")):
        try:
            raw = json.loads(json_file.read_text(encoding="utf-8"))
            fw = _parse_framework(raw)
            _frameworks[fw.id] = fw
            q_count = sum(len(ind.questions) for ind in fw.indicators)
            logger.info("Loaded framework: %s (%d questions)", fw.id, q_count)
        except Exception as exc:
            logger.error("Failed to load framework from %s: %s", json_file.name, exc)

    _loaded = True
    logger.info("Total frameworks loaded: %d", len(_frameworks))
    return _frameworks


def get_framework(framework_id: str) -> Optional[Framework]:
    """Get a single framework by ID."""
    if not _loaded:
        load_all_frameworks()
    return _frameworks.get(framework_id)


def list_frameworks(
    category: Optional[str] = None,
    status: Optional[str] = None,
) -> list[Framework]:
    """List all frameworks, optionally filtered by category and/or status."""
    if not _loaded:
        load_all_frameworks()
    result = list(_frameworks.values())
    if category:
        result = [f for f in result if f.category.value == category]
    if status:
        result = [f for f in result if f.status.value == status]
    return result


def get_question_map(framework_id: str) -> dict[str, Question]:
    """Get a flat question_id -> Question mapping for a framework."""
    fw = get_framework(framework_id)
    if fw is None:
        return {}
    qmap: dict[str, Question] = {}
    for ind in fw.indicators:
        for q in ind.questions:
            qmap[q.id] = q
    return qmap


def search_frameworks(keyword: str) -> list[Framework]:
    """Search frameworks by keyword in name, organization, or description."""
    if not _loaded:
        load_all_frameworks()
    kw = keyword.lower()
    results = []
    for fw in _frameworks.values():
        if (
            kw in fw.name.lower()
            or kw in fw.organization.lower()
            or kw in fw.description.lower()
            or (fw.standard_code and kw in fw.standard_code.lower())
        ):
            results.append(fw)
    return results


def recommend_frameworks(company_size: str) -> list[Framework]:
    """Recommend frameworks that support the given company size."""
    if not _loaded:
        load_all_frameworks()
    try:
        size = CompanySize(company_size)
    except ValueError:
        return []
    return [fw for fw in _frameworks.values() if size in fw.supported_sizes]


def reload_frameworks() -> dict[str, Framework]:
    """Force-reload all frameworks from disk."""
    global _loaded
    _loaded = False
    return load_all_frameworks()
