"""Tests for the DDW ESG Assessment plugin."""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
import types

# ---------------------------------------------------------------------------
# Bootstrap: load the plugin package from a hyphenated directory name
# so that `from ddw_esg_assessment.xxx import yyy` works even though
# the directory is named `ddw-esg-assessment`.
# ---------------------------------------------------------------------------
_PKG_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PKG_NAME = "ddw_esg_assessment"

if _PKG_NAME not in sys.modules:
    # Create a package object first (so relative imports work)
    _pkg = types.ModuleType(_PKG_NAME)
    _pkg.__path__ = [_PKG_DIR]
    _pkg.__package__ = _PKG_NAME
    _pkg.__file__ = os.path.join(_PKG_DIR, "__init__.py")
    sys.modules[_PKG_NAME] = _pkg

    # Now load __init__.py into the package module
    _init_spec = importlib.util.spec_from_file_location(
        _PKG_NAME,
        _pkg.__file__,
        submodule_search_locations=[_PKG_DIR],
    )
    _init_mod = importlib.util.module_from_spec(_init_spec)
    _init_mod.__name__ = _PKG_NAME
    _init_mod.__package__ = _PKG_NAME
    _init_mod.__path__ = [_PKG_DIR]
    _init_mod.__file__ = _pkg.__file__
    sys.modules[_PKG_NAME] = _init_mod
    _init_spec.loader.exec_module(_init_mod)

    # Register sub-modules so that `from ddw_esg_assessment.xxx import yyy` works
    for _sub in ("models", "scoring", "skip_engine", "benchmark", "routes"):
        _sub_path = os.path.join(_PKG_DIR, f"{_sub}.py")
        if os.path.isfile(_sub_path):
            _sub_fqn = f"{_PKG_NAME}.{_sub}"
            _sub_spec = importlib.util.spec_from_file_location(_sub_fqn, _sub_path)
            _sub_mod = importlib.util.module_from_spec(_sub_spec)
            _sub_mod.__package__ = _PKG_NAME
            sys.modules[_sub_fqn] = _sub_mod
            _sub_spec.loader.exec_module(_sub_mod)

import pytest  # noqa: E402

# Import the plugin registration and models
from plugins.ddw_esg_assessment import register  # noqa: E402
from plugins.ddw_esg_assessment.benchmark import (  # noqa: E402
    benchmark_cdp,
    benchmark_csi_esg,
    benchmark_ecovadis,
    benchmark_msci,
    benchmark_own,
    benchmark_sp_csa,
    calculate_all_benchmarks,
)
from plugins.ddw_esg_assessment.models import get_store  # noqa: E402
from plugins.ddw_esg_assessment.scoring import (  # noqa: E402
    calculate_scores_by_framework,
    get_score_level,
    get_score_level_en,
    round_half_up,
)
from plugins.ddw_esg_assessment.skip_engine import (  # noqa: E402
    compute_visibility,
    evaluate_skip_rules,
)
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_store():
    """Clear in-memory store between tests."""
    store = get_store()
    store.clear()
    yield
    store.clear()


@pytest.fixture
def app():
    """Create a test FastAPI app with the plugin registered."""
    test_app = FastAPI()
    register(test_app)
    return test_app


@pytest.fixture
def client(app):
    """HTTP test client."""
    return TestClient(app)


@pytest.fixture
def sample_answers():
    """All questions answered with max score (4)."""
    return {
        "E1": 4, "E2": 4, "E3": 4, "E4": 4,
        "S1": 4, "S2": 4, "S3": 4,
        "G1": 4, "G2": 4, "G3": 4,
    }


@pytest.fixture
def sample_answers_low():
    """All questions answered with low score (1)."""
    return {
        "E1": 1, "E2": 1, "E3": 1, "E4": 1,
        "S1": 1, "S2": 1, "S3": 1,
        "G1": 1, "G2": 1, "G3": 1,
    }


# ---------------------------------------------------------------------------
# Unit tests: scoring.py
# ---------------------------------------------------------------------------


class TestRoundHalfUp:
    def test_basic(self):
        assert round_half_up(0.0) == 0
        assert round_half_up(1.5) == 2
        assert round_half_up(100.0) == 100

    def test_negative(self):
        assert round_half_up(-1.5) == -2
        assert round_half_up(-2.5) == -3  # ROUND_HALF_UP rounds away from zero


class TestScoreLevels:
    def test_excellent(self):
        assert get_score_level(81) == "优秀"
        assert get_score_level(100) == "优秀"

    def test_good(self):
        assert get_score_level(61) == "良好"
        assert get_score_level(80) == "良好"

    def test_medium(self):
        assert get_score_level(41) == "中等"

    def test_poor(self):
        assert get_score_level(21) == "待改进"

    def test_fail(self):
        assert get_score_level(0) == "不合格"
        assert get_score_level(20) == "不合格"

    def test_en_levels(self):
        assert get_score_level_en(80) == "excellent"
        assert get_score_level_en(60) == "good"
        assert get_score_level_en(40) == "medium"
        assert get_score_level_en(20) == "poor"
        assert get_score_level_en(0) == "fail"


class TestCalculateScores:
    def test_all_max_scores(self, sample_answers):
        questions = [
            {"id": "Q1", "theme_id": "T1", "max_score": 4},
            {"id": "Q2", "theme_id": "T1", "max_score": 4},
            {"id": "Q3", "theme_id": "T2", "max_score": 4},
        ]
        answers = {"Q1": 4, "Q2": 4, "Q3": 4}
        result = calculate_scores_by_framework(questions, answers)
        assert result["total_score"] == 100
        assert result["grade"] == "excellent"
        assert result["level_cn"] == "优秀"

    def test_all_zero(self):
        questions = [
            {"id": "Q1", "theme_id": "T1", "max_score": 4},
        ]
        result = calculate_scores_by_framework(questions, {})
        assert result["total_score"] == 0
        assert result["grade"] == "fail"

    def test_partial_answers(self):
        questions = [
            {"id": "Q1", "theme_id": "T1", "max_score": 4},
            {"id": "Q2", "theme_id": "T1", "max_score": 4},
        ]
        answers = {"Q1": 2}
        result = calculate_scores_by_framework(questions, answers)
        assert result["theme_scores"]["T1"] == 50
        assert result["total_score"] == 50

    def test_weighted_themes(self):
        questions = [
            {"id": "Q1", "theme_id": "T1", "max_score": 4},
            {"id": "Q2", "theme_id": "T2", "max_score": 4},
        ]
        answers = {"Q1": 4, "Q2": 0}
        weights = {"T1": 3.0, "T2": 1.0}
        result = calculate_scores_by_framework(questions, answers, weights)
        assert result["total_score"] == 75

    def test_indicator_scores(self):
        questions = [
            {"id": "Q1", "theme_id": "T1", "max_score": 4},
        ]
        answers = {"Q1": 3}
        result = calculate_scores_by_framework(questions, answers)
        assert result["indicator_scores"]["Q1"] == 75


# ---------------------------------------------------------------------------
# Unit tests: skip_engine.py
# ---------------------------------------------------------------------------


class TestSkipEngine:
    def test_forward_skip(self):
        question = {
            "id": "Q1",
            "skip_rules": [
                {"type": "forward_skip", "target": ["Q2", "Q3"]}
            ],
        }
        result = evaluate_skip_rules(question, {})
        assert result["skipped_ids"] == ["Q2", "Q3"]
        assert result["has_skip"] is True

    def test_forward_jump(self):
        question = {
            "id": "Q1",
            "skip_rules": [
                {"type": "forward_jump", "target": "Q5"}
            ],
        }
        result = evaluate_skip_rules(question, {})
        assert result["jump_to"] == "Q5"
        assert result["has_skip"] is True

    def test_conditional_show_met(self):
        question = {
            "id": "Q1",
            "skip_rules": [
                {"type": "conditional_show", "condition": {"operator": ">=", "target": 3}, "target": None}
            ],
        }
        result = evaluate_skip_rules(question, {"Q1": 4})
        assert result["has_skip"] is False

    def test_conditional_show_skip(self):
        question = {
            "id": "Q1",
            "skip_rules": [
                {"type": "conditional_show", "condition": {"operator": ">=", "target": 3}, "target": ["Q2"]}
            ],
        }
        result = evaluate_skip_rules(question, {"Q1": 4})
        assert result["skipped_ids"] == ["Q2"]
        assert result["has_skip"] is True

    def test_branch(self):
        question = {
            "id": "Q1",
            "skip_rules": [
                {"type": "branch", "condition": {"operator": "==", "target": 1}, "target": "Q3"}
            ],
        }
        result = evaluate_skip_rules(question, {"Q1": 1})
        assert result["jump_to"] == "Q3"

    def test_no_rules(self):
        question = {"id": "Q1", "skip_rules": []}
        result = evaluate_skip_rules(question, {})
        assert result["has_skip"] is False
        assert result["skipped_ids"] == []

    def test_compute_visibility(self):
        questions = [
            {"id": "Q1", "theme_id": "T1", "dimension": "E", "skip_rules": [
                {"type": "forward_skip", "target": ["Q2"]}
            ]},
            {"id": "Q2", "theme_id": "T1", "dimension": "E", "skip_rules": []},
            {"id": "Q3", "theme_id": "T1", "dimension": "E", "skip_rules": []},
        ]
        answers = {"Q1": 2}
        result = compute_visibility(questions, answers)
        assert "Q1" in result["visible_ids"]
        assert "Q2" in result["skipped_ids"]
        assert "Q3" in result["visible_ids"]

    def test_compute_visibility_with_dimension(self):
        questions = [
            {"id": "Q1", "theme_id": "T1", "dimension": "E", "skip_rules": []},
            {"id": "Q2", "theme_id": "T1", "dimension": "S", "skip_rules": []},
        ]
        result = compute_visibility(questions, {}, dimension="E")
        assert result["visible_ids"] == ["Q1"]
        assert "Q2" not in result["visible_ids"]


# ---------------------------------------------------------------------------
# Unit tests: benchmark.py
# ---------------------------------------------------------------------------


class TestBenchmark:
    def test_own_platinum(self):
        assert benchmark_own(80)["level"] == "铂金"

    def test_own_gold(self):
        assert benchmark_own(65)["level"] == "金牌"

    def test_own_silver(self):
        assert benchmark_own(45)["level"] == "银牌"

    def test_own_bronze(self):
        assert benchmark_own(30)["level"] == "铜牌"

    def test_own_below(self):
        assert benchmark_own(10)["level"] == "未达标"

    def test_ecovadis_boundary_platinum(self):
        result_at_70 = benchmark_ecovadis(70.0, {"E": 50, "S": 50, "G": 50})
        assert result_at_70["level"] == "Platinum"
        assert result_at_70["medal"] == "Platinum"

        result_at_69 = benchmark_ecovadis(69.9, {"E": 50, "S": 50, "G": 50})
        assert result_at_69["level"] == "Gold"
        assert result_at_69["medal"] == "Gold"

    def test_ecovadis_gold_min_dims(self):
        result = benchmark_ecovadis(60.0, {"E": 30, "S": 30, "G": 25})
        assert result["level"] == "Silver"

    def test_ecovadis_insufficient(self):
        result = benchmark_ecovadis(10.0, {"E": 5, "S": 5})
        assert result["level"] == "Insufficient"

    def test_cdp_a(self):
        assert benchmark_cdp(80)["grade"] == "A"

    def test_cdp_f(self):
        assert benchmark_cdp(10)["grade"] == "F"

    def test_msci_aaa(self):
        assert benchmark_msci(85)["grade"] == "AAA"

    def test_msci_ccc(self):
        assert benchmark_msci(30)["grade"] == "CCC"

    def test_sp_csa_top10(self):
        assert benchmark_sp_csa(85)["rating"] == "Top 10%"

    def test_sp_csa_bottom(self):
        assert benchmark_sp_csa(10)["rating"] == "Bottom"

    def test_csi_esg_aaa(self):
        assert benchmark_csi_esg(90)["grade"] == "AAA"

    def test_csi_esg_c(self):
        assert benchmark_csi_esg(10)["grade"] == "C"

    def test_calculate_all_benchmarks(self):
        results = calculate_all_benchmarks(75.0, {"E": 80, "S": 70, "G": 60})
        assert "own" in results
        assert "ecovadis" in results
        assert "cdp" in results
        assert "msci" in results
        assert "sp_csa" in results
        assert "csi_esg" in results


# ---------------------------------------------------------------------------
# Integration tests: API endpoints
# ---------------------------------------------------------------------------


class TestHealthCheck:
    def test_health_check(self, client):
        response = client.get("/api/v1/plugins/ddw-esg-assessment/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["plugin"] == "ddw-esg-assessment"


class TestCreateAssessment:
    def test_create_assessment(self, client):
        response = client.post(
            "/api/v1/plugins/ddw-esg-assessment/assessments",
            json={
                "user_id": "test-user-1",
                "framework_id": "ecovadis",
                "company_name": "Test Corp",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "test-user-1"
        assert data["framework_id"] == "ecovadis"
        assert data["status"] == "in_progress"
        assert "id" in data


class TestSubmitAnswer:
    def test_submit_answer(self, client):
        create_resp = client.post(
            "/api/v1/plugins/ddw-esg-assessment/assessments",
            json={"user_id": "u1", "framework_id": "ecovadis"},
        )
        assessment_id = create_resp.json()["id"]

        answer_resp = client.post(
            f"/api/v1/plugins/ddw-esg-assessment/assessments/{assessment_id}/answers",
            json={"question_id": "E1", "value": 3},
        )
        assert answer_resp.status_code == 200
        assert answer_resp.json()["answers"]["E1"] == 3

    def test_submit_answer_not_found(self, client):
        response = client.post(
            "/api/v1/plugins/ddw-esg-assessment/assessments/nonexistent/answers",
            json={"question_id": "E1", "value": 3},
        )
        assert response.status_code == 404


class TestCalculateScoresAPI:
    def test_calculate_scores(self, client):
        create_resp = client.post(
            "/api/v1/plugins/ddw-esg-assessment/assessments",
            json={"user_id": "u1", "framework_id": "ecovadis"},
        )
        assessment_id = create_resp.json()["id"]

        answers = {
            "E1": 4, "E2": 4, "E3": 4, "E4": 4,
            "S1": 4, "S2": 4, "S3": 4,
            "G1": 4, "G2": 4, "G3": 4,
        }
        for qid, val in answers.items():
            client.post(
                f"/api/v1/plugins/ddw-esg-assessment/assessments/{assessment_id}/answers",
                json={"question_id": qid, "value": val},
            )

        calc_resp = client.post(
            f"/api/v1/plugins/ddw-esg-assessment/assessments/{assessment_id}/calculate",
        )
        assert calc_resp.status_code == 200
        data = calc_resp.json()
        assert data["total_score"] == 100
        assert data["grade"] == "excellent"
        assert data["level_cn"] == "优秀"
        assert "own" in data["benchmark_results"]
        assert "ecovadis" in data["benchmark_results"]


class TestBenchmarkEcoVadisBoundary:
    def test_boundary_69_9_gold(self, client):
        results = calculate_all_benchmarks(69.9, {"E": 50, "S": 50, "G": 50})
        assert results["ecovadis"]["level"] == "Gold"

    def test_boundary_70_0_platinum(self, client):
        results = calculate_all_benchmarks(70.0, {"E": 50, "S": 50, "G": 50})
        assert results["ecovadis"]["level"] == "Platinum"


class TestListAssessments:
    def test_list_assessments(self, client):
        client.post(
            "/api/v1/plugins/ddw-esg-assessment/assessments",
            json={"user_id": "u1", "framework_id": "ecovadis"},
        )
        client.post(
            "/api/v1/plugins/ddw-esg-assessment/assessments",
            json={"user_id": "u1", "framework_id": "cdp"},
        )
        client.post(
            "/api/v1/plugins/ddw-esg-assessment/assessments",
            json={"user_id": "u2", "framework_id": "ecovadis"},
        )

        response = client.get("/api/v1/plugins/ddw-esg-assessment/assessments?user_id=u1")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all(a["user_id"] == "u1" for a in data)


class TestDeleteAssessment:
    def test_delete_assessment(self, client):
        create_resp = client.post(
            "/api/v1/plugins/ddw-esg-assessment/assessments",
            json={"user_id": "u1", "framework_id": "ecovadis"},
        )
        assessment_id = create_resp.json()["id"]

        del_resp = client.delete(f"/api/v1/plugins/ddw-esg-assessment/assessments/{assessment_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["status"] == "deleted"

        get_resp = client.get(f"/api/v1/plugins/ddw-esg-assessment/assessments/{assessment_id}")
        assert get_resp.status_code == 404

    def test_delete_not_found(self, client):
        response = client.delete("/api/v1/plugins/ddw-esg-assessment/assessments/nonexistent")
        assert response.status_code == 404


class TestFrameworks:
    def test_list_frameworks(self, client):
        response = client.get("/api/v1/plugins/ddw-esg-assessment/frameworks")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 6
        ids = {f["id"] for f in data}
        assert "ecovadis" in ids
        assert "cdp" in ids
        assert "msci" in ids


class TestQuestionBankMeta:
    def test_meta(self, client):
        response = client.get("/api/v1/plugins/ddw-esg-assessment/question-bank/meta")
        assert response.status_code == 200
        data = response.json()
        assert data["total_questions"] == 10
        assert len(data["dimensions"]) == 3
        assert len(data["themes"]) == 3
