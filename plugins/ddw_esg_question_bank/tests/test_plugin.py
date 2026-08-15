"""Tests for the ddw-esg-question-bank plugin.

Uses FastAPI TestClient with httpx AsyncClient pattern for async testing.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from plugins.ddw_esg_question_bank import register as register_plugin

# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def app() -> FastAPI:
    """Create a FastAPI app with the ESG question bank plugin registered."""
    test_app = FastAPI()
    register_plugin(test_app)
    return test_app


@pytest.fixture
def client(app: FastAPI) -> AsyncClient:
    """Create an async test client."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ── Health Check ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient) -> None:
    """GET /health returns status ok."""
    response = await client.get("/api/v1/plugins/ddw-esg-question-bank/health")
    assert response.status_code == 200
    data = response.json()
    assert data["plugin"] == "ddw-esg-question-bank"
    assert data["status"] == "ok"
    assert data["frameworks_loaded"] >= 10  # At least 10 frameworks


# ── List Frameworks ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_frameworks(client: AsyncClient) -> None:
    """GET /frameworks returns a list of frameworks."""
    response = await client.get("/api/v1/plugins/ddw-esg-question-bank/frameworks")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 10  # At least 10 frameworks
    # Check structure of first framework
    fw = data[0]
    assert "id" in fw
    assert "name" in fw
    assert "question_count" in fw
    assert fw["question_count"] > 0


@pytest.mark.asyncio
async def test_list_frameworks_filter_category(client: AsyncClient) -> None:
    """GET /frameworks?category=international filters correctly."""
    response = await client.get(
        "/api/v1/plugins/ddw-esg-question-bank/frameworks",
        params={"category": "international"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    for fw in data:
        assert fw["category"] == "international"


@pytest.mark.asyncio
async def test_list_frameworks_filter_status(client: AsyncClient) -> None:
    """GET /frameworks?status=available filters correctly."""
    response = await client.get(
        "/api/v1/plugins/ddw-esg-question-bank/frameworks",
        params={"status": "available"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    for fw in data:
        assert fw["status"] == "available"


# ── Framework Detail ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_framework_detail(client: AsyncClient) -> None:
    """GET /frameworks/standard-esg returns detail with themes and indicators."""
    response = await client.get(
        "/api/v1/plugins/ddw-esg-question-bank/frameworks/standard-esg"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "standard-esg"
    assert data["name"] == "Standard ESG 综合评估框架"
    assert len(data["themes"]) == 3  # E, S, G
    assert len(data["indicators"]) >= 12  # E1-E4, S1-S4, G1-G4 + extras


@pytest.mark.asyncio
async def test_framework_detail_not_found(client: AsyncClient) -> None:
    """GET /frameworks/nonexistent returns 404."""
    response = await client.get(
        "/api/v1/plugins/ddw-esg-question-bank/frameworks/nonexistent"
    )
    assert response.status_code == 404


# ── Framework Questions ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_framework_questions(client: AsyncClient) -> None:
    """GET /frameworks/standard-esg/questions returns questions."""
    response = await client.get(
        "/api/v1/plugins/ddw-esg-question-bank/frameworks/standard-esg/questions"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["framework_id"] == "standard-esg"
    assert data["total"] >= 40  # At least 40 questions
    assert len(data["questions"]) >= 40
    # Check question structure
    q = data["questions"][0]
    assert "id" in q
    assert "text" in q
    assert "type" in q
    assert "options" in q
    assert len(q["options"]) == 5  # Likert5 has 5 options


@pytest.mark.asyncio
async def test_question_filter_by_theme(client: AsyncClient) -> None:
    """GET /frameworks/standard-esg/questions?theme_id=E filters by theme."""
    response = await client.get(
        "/api/v1/plugins/ddw-esg-question-bank/frameworks/standard-esg/questions",
        params={"theme_id": "E"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["framework_id"] == "standard-esg"
    # All questions should be in theme E
    for q in data["questions"]:
        assert q["theme_id"] == "E"


@pytest.mark.asyncio
async def test_question_filter_by_indicator(client: AsyncClient) -> None:
    """GET /frameworks/standard-esg/questions?indicator_code=E1 filters by indicator."""
    response = await client.get(
        "/api/v1/plugins/ddw-esg-question-bank/frameworks/standard-esg/questions",
        params={"indicator_code": "E1"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["framework_id"] == "standard-esg"
    # All questions should be in indicator E1
    for q in data["questions"]:
        assert q["indicator_code"] == "E1"
    assert len(data["questions"]) == 4  # E1 has 4 questions


# ── Question Bank Meta ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_question_bank_meta(client: AsyncClient) -> None:
    """GET /frameworks/standard-esg/meta returns metadata."""
    response = await client.get(
        "/api/v1/plugins/ddw-esg-question-bank/frameworks/standard-esg/meta"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["framework_id"] == "standard-esg"
    assert data["total_questions"] >= 40
    assert data["total_indicators"] >= 12
    assert data["total_themes"] == 3
    assert len(data["themes"]) == 3
    assert len(data["indicators"]) >= 12


# ── Assessment ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_assess(client: AsyncClient) -> None:
    """POST /assess with answers returns scores."""
    # Create answers for all E1 questions (4 questions, value 3 each)
    answers = [
        {"question_id": "E1-Q1", "value": 3},
        {"question_id": "E1-Q2", "value": 4},
        {"question_id": "E1-Q3", "value": 3},
        {"question_id": "E1-Q4", "value": 3},
    ]
    payload = {
        "framework_id": "standard-esg",
        "answers": answers,
    }
    response = await client.post(
        "/api/v1/plugins/ddw-esg-question-bank/assess",
        json=payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["framework_id"] == "standard-esg"
    assert isinstance(data["total_score"], (int, float))
    assert 0 <= data["total_score"] <= 100
    assert data["level"] in ["excellent", "good", "medium", "poor", "fail"]
    assert data["level_label"] in ["优秀", "良好", "中等", "待改进", "不合格"]
    assert data["level_color"].startswith("#")
    assert isinstance(data["theme_scores"], list)
    assert isinstance(data["indicator_scores"], list)
    assert data["total_questions"] >= 40
    assert data["answered_questions"] == 4
    assert 0 <= data["completion_rate"] <= 100


@pytest.mark.asyncio
async def test_assess_perfect_score(client: AsyncClient) -> None:
    """POST /assess with all max values returns excellent score."""
    # Get all questions first
    response = await client.get(
        "/api/v1/plugins/ddw-esg-question-bank/frameworks/standard-esg/questions"
    )
    questions = response.json()["questions"]
    # Answer all with max value (5)
    answers = [{"question_id": q["id"], "value": 5} for q in questions]
    payload = {
        "framework_id": "standard-esg",
        "answers": answers,
    }
    response = await client.post(
        "/api/v1/plugins/ddw-esg-question-bank/assess",
        json=payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_score"] == 100
    assert data["level"] == "excellent"
    assert data["completion_rate"] == 100


@pytest.mark.asyncio
async def test_assess_low_score(client: AsyncClient) -> None:
    """POST /assess with all min values returns fail score."""
    # Get all questions first
    response = await client.get(
        "/api/v1/plugins/ddw-esg-question-bank/frameworks/standard-esg/questions"
    )
    questions = response.json()["questions"]
    # Answer all with min value (1)
    answers = [{"question_id": q["id"], "value": 1} for q in questions]
    payload = {
        "framework_id": "standard-esg",
        "answers": answers,
    }
    response = await client.post(
        "/api/v1/plugins/ddw-esg-question-bank/assess",
        json=payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_score"] == 20
    assert data["level"] == "poor"
    assert data["completion_rate"] == 100


# ── Score Levels ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_score_levels(client: AsyncClient) -> None:
    """GET /assess/levels returns score level definitions."""
    response = await client.get(
        "/api/v1/plugins/ddw-esg-question-bank/assess/levels"
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 5
    codes = {level["code"] for level in data}
    assert codes == {"excellent", "good", "medium", "poor", "fail"}
    # Check structure
    for level in data:
        assert "label" in level
        assert "label_en" in level
        assert "min" in level
        assert "max" in level
        assert "color" in level
        assert "description" in level


# ── Search ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search(client: AsyncClient) -> None:
    """GET /search?q=ISO returns frameworks matching the keyword."""
    response = await client.get(
        "/api/v1/plugins/ddw-esg-question-bank/search",
        params={"q": "ISO"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2  # ISO14001 and ISO45001 at minimum
    for result in data:
        assert "id" in result
        assert "name" in result
        assert "relevance_score" in result


@pytest.mark.asyncio
async def test_search_ecovadis(client: AsyncClient) -> None:
    """GET /search?q=EcoVadis returns the EcoVadis framework."""
    response = await client.get(
        "/api/v1/plugins/ddw-esg-question-bank/search",
        params={"q": "EcoVadis"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any("ecovadis" in r["id"].lower() for r in data)


# ── Recommend ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recommend(client: AsyncClient) -> None:
    """GET /recommend?company_size=medium returns suitable frameworks."""
    response = await client.get(
        "/api/v1/plugins/ddw-esg-question-bank/recommend",
        params={"company_size": "medium"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 5  # Most frameworks support medium
    for result in data:
        assert "id" in result
        assert "name" in result
        assert "question_count" in result


@pytest.mark.asyncio
async def test_recommend_enterprise(client: AsyncClient) -> None:
    """GET /recommend?company_size=enterprise returns suitable frameworks."""
    response = await client.get(
        "/api/v1/plugins/ddw-esg-question-bank/recommend",
        params={"company_size": "enterprise"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 8  # Most frameworks support enterprise


# ── Ecovadis Framework ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ecovadis_framework(client: AsyncClient) -> None:
    """GET /frameworks/ecovadis returns EcoVadis framework detail."""
    response = await client.get(
        "/api/v1/plugins/ddw-esg-question-bank/frameworks/ecovadis"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "ecovadis"
    assert data["name"] == "EcoVadis 企业社会责任评估"
    assert len(data["themes"]) == 4  # EN, LH, ET, SP


@pytest.mark.asyncio
async def test_ecovadis_questions(client: AsyncClient) -> None:
    """GET /frameworks/ecovadis/questions returns EcoVadis questions."""
    response = await client.get(
        "/api/v1/plugins/ddw-esg-question-bank/frameworks/ecovadis/questions"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["framework_id"] == "ecovadis"
    assert data["total"] >= 40  # At least 40 questions


# ── Draft Frameworks ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_draft_frameworks_exist(client: AsyncClient) -> None:
    """All draft frameworks should be accessible."""
    draft_ids = [
        "iso14001", "iso45001", "gri", "cdp", "sasb",
        "tcfd", "gb-t36000", "gb-t24067",
    ]
    for fw_id in draft_ids:
        response = await client.get(
            f"/api/v1/plugins/ddw-esg-question-bank/frameworks/{fw_id}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == fw_id
        assert data["status"] == "draft"
