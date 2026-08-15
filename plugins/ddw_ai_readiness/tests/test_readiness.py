"""ddw_ai_readiness 测试用例（10 条）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from plugins.ddw_ai_readiness.services import (
    get_stats,
    get_submission,
    list_submissions,
    save_submission,
    score_submission,
)


@pytest.fixture(autouse=True)
def _tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """每个测试使用独立临时数据库。"""
    db_path = tmp_path / "readiness.db"
    monkeypatch.setattr("plugins.ddw_ai_readiness.services.DB_PATH", db_path)
    yield


# ---------- 1. test_high_readiness_grade_a ----------
def test_high_readiness_grade_a():
    data = {
        "q1": 3, "q2": 3, "q3": 2, "q4": 3, "q5": 2, "q7": 2,
        "d": {
            "D1": {"a": 2, "b": 2, "c": 2},
            "D2": {"a": 2, "b": 2, "c": 2},
            "D3": {"a": 2, "b": 2, "c": 2},
            "D4": {"a": 2, "b": 2, "c": 2},
        },
        "scenes": ["S5", "S1", "S3"],
    }
    result = score_submission(data)
    assert result["score1"] == 15
    assert result["grade1"] == "A"
    assert result["veto"] is False
    assert result["grade"] == "A级"


# ---------- 2. test_veto_rule ----------
def test_veto_rule():
    data = {"q1": 0, "q2": 3, "q3": 0, "q4": 3, "q5": 3, "q7": 3}
    result = score_submission(data)
    assert result["veto"] is True
    assert result["grade1"] == "C"


# ---------- 3. test_low_score_grade_c ----------
def test_low_score_grade_c():
    data = {"q1": 0, "q2": 0, "q3": 0, "q4": 0, "q5": 0, "q7": 0}
    result = score_submission(data)
    assert result["score1"] == 0
    assert result["grade1"] == "C"
    assert result["grade"] == "C级"


# ---------- 4. test_mid_score_grade_b ----------
def test_mid_score_grade_b():
    data = {"q1": 2, "q2": 1, "q3": 1, "q4": 1, "q5": 1, "q7": 1}
    result = score_submission(data)
    assert result["score1"] == 7
    assert result["grade1"] == "B"


# ---------- 5. test_score2_computation ----------
def test_score2_computation():
    data = {
        "q1": 1, "q2": 1, "q3": 1, "q4": 1, "q5": 1, "q7": 1,
        "d": {
            "D1": {"a": 2, "b": 2, "c": 2},
            "D2": {"a": 0, "b": 0, "c": 0},
            "D3": {"a": 0, "b": 0, "c": 0},
            "D4": {"a": 0, "b": 0, "c": 0},
        },
    }
    result = score_submission(data)
    assert result["score2"] == 6


# ---------- 6. test_missing_q_raises ----------
def test_missing_q_raises():
    data = {"q1": 1, "q2": 1, "q3": 1, "q4": None, "q5": 1, "q7": 1}
    with pytest.raises(ValueError, match="q1-q5/q7 必须为有效整数"):
        score_submission(data)


# ---------- 7. test_submission_persist ----------
def test_submission_persist():
    payload = {
        "company": "测试公司",
        "name": "张三",
        "phone": "13800138000",
        "q1": 2, "q2": 2, "q3": 1, "q4": 2, "q5": 2, "q7": 2,
        "q6": ["选项A", "选项B"],
        "d": {"D1": {"a": 1, "b": 1, "c": 1}},
        "scenes": ["S1", "S2"],
    }
    scores = score_submission(payload)
    sid = save_submission(payload, scores)
    row = get_submission(sid)
    assert row is not None
    assert row["company"] == "测试公司"
    assert row["name"] == "张三"
    assert row["phone"] == "13800138000"
    assert row["q1"] == 2
    assert row["q6"] == ["选项A", "选项B"]
    assert row["d"] == {"D1": {"a": 1, "b": 1, "c": 1}}
    assert row["scenes"] == ["S1", "S2"]
    assert row["score1"] == scores["score1"]
    assert row["grade1"] == scores["grade1"]


# ---------- 8. test_list_and_stats ----------
def test_list_and_stats():
    # 插入 A 级
    payload_a = {"q1": 3, "q2": 3, "q3": 2, "q4": 3, "q5": 2, "q7": 2}
    scores_a = score_submission(payload_a)
    save_submission(payload_a, scores_a)

    # 插入 B 级
    payload_b = {"q1": 2, "q2": 1, "q3": 1, "q4": 1, "q5": 1, "q7": 1}
    scores_b = score_submission(payload_b)
    save_submission(payload_b, scores_b)

    # 插入 C 级
    payload_c = {"q1": 0, "q2": 0, "q3": 0, "q4": 0, "q5": 0, "q7": 0}
    scores_c = score_submission(payload_c)
    save_submission(payload_c, scores_c)

    # list 返回 3 条倒序
    rows = list_submissions(limit=10)
    assert len(rows) == 3
    assert rows[0]["id"] > rows[1]["id"] > rows[2]["id"]

    # stats 计数
    stats = get_stats()
    assert stats["total"] == 3
    assert stats["grade_a"] == 1
    assert stats["grade_b"] == 1
    assert stats["grade_c"] == 1
    assert stats["grade1_a"] == 1
    assert stats["grade1_b"] == 1
    assert stats["grade1_c"] == 1


# ---------- 9. test_invalid_scenes_filtered ----------
def test_invalid_scenes_filtered():
    payload = {
        "q1": 1, "q2": 1, "q3": 1, "q4": 1, "q5": 1, "q7": 1,
        "scenes": ["S99", "S1"],
    }
    scores = score_submission(payload)
    sid = save_submission(payload, scores)
    row = get_submission(sid)
    assert row is not None
    assert row["scenes"] == ["S1"]


# ---------- 10. test_api_endpoints ----------
def test_api_endpoints():
    from fastapi import FastAPI

    from plugins.ddw_ai_readiness.router import build_router

    app = FastAPI()
    app.include_router(build_router())
    client = TestClient(app)

    # POST /submissions 200
    resp = client.post(
        "/api/v1/plugins/ddw_ai_readiness/submissions",
        json={"q1": 2, "q2": 2, "q3": 1, "q4": 2, "q5": 2, "q7": 2},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert "score1" in data

    # GET /stats 需登录（商机数据不公开）
    from core.auth.jwt import current_user as _cu
    app.dependency_overrides[_cu] = lambda: {"username": "tester"}
    resp = client.get("/api/v1/plugins/ddw_ai_readiness/stats")
    assert resp.status_code == 200
    stats = resp.json()
    assert "total" in stats

    # GET /health 200
    resp = client.get("/api/v1/plugins/ddw_ai_readiness/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
