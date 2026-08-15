"""化工安全合规助手 — pytest 测试用例"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import sys
from pathlib import Path

# 确保插件目录在 Python path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from plugins.ddw_chem_safety.plugin import Plugin
from plugins.ddw_chem_safety import storage


@pytest.fixture
def app(tmp_path):
    """创建测试用 FastAPI 应用，使用临时数据库"""
    db_path = tmp_path / "test_chem_safety.db"
    storage.DB_PATH = db_path
    _app = FastAPI()
    Plugin(_app, config={})
    return _app


@pytest.fixture
def client(app):
    """创建测试客户端"""
    return TestClient(app)


# ═══════════════════════════════════════
# TC-1: 健康检查
# ═══════════════════════════════════════


class TestHealthCheck:

    def test_health_returns_ok(self, client):
        resp = client.get("/api/v1/plugins/ddw_chem_safety/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["plugin_name"] == "ddw_chem_safety"
        assert data["version"] == "1.0.0"
        assert data["status"] == "healthy"


# ═══════════════════════════════════════
# TC-2/3: 安全法规问答
# ═══════════════════════════════════════


class TestRegulationQA:

    def test_ask_returns_answer(self, client):
        resp = client.post("/api/v1/plugins/ddw_chem_safety/regulation/ask", json={
            "question": "化工企业动火作业需要办理什么手续？"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert len(data["sources"]) > 0
        assert 0 <= data["confidence"] <= 1

    def test_ask_with_context(self, client):
        resp = client.post("/api/v1/plugins/ddw_chem_safety/regulation/ask", json={
            "question": "受限空间作业的氧含量要求是多少？",
            "context": "我厂磷酸车间储罐清洗作业"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "19.5" in data["answer"] or "23.5" in data["answer"]


# ═══════════════════════════════════════
# TC-4/5/6: 隐患上报与状态流转
# ═══════════════════════════════════════


class TestHazardReport:

    def test_create_hazard_report(self, client):
        resp = client.post("/api/v1/plugins/ddw_chem_safety/hazard/report", json={
            "area": "磷酸车间A区",
            "hazard_type": "化学品隐患",
            "description": "硫酸储罐底部发现轻微渗漏",
            "reporter": "张三"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "待处理"
        assert data["id"] > 0

    def test_hazard_status_transition(self, client):
        create_resp = client.post("/api/v1/plugins/ddw_chem_safety/hazard/report", json={  # noqa: E501
            "area": "仓库B区",
            "hazard_type": "消防隐患",
            "description": "灭火器过期",
            "reporter": "李四"
        })
        hazard_id = create_resp.json()["id"]

        resp = client.put(f"/api/v1/plugins/ddw_chem_safety/hazard/{hazard_id}/status", json={  # noqa: E501
            "status": "整改中",
            "resolution_note": "已联系消防部门更换灭火器"
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "整改中"

    def test_hazard_close_records_time(self, client):
        create_resp = client.post("/api/v1/plugins/ddw_chem_safety/hazard/report", json={  # noqa: E501
            "area": "配电室",
            "hazard_type": "电气隐患",
            "description": "配电柜门未关闭",
            "reporter": "王五"
        })
        hazard_id = create_resp.json()["id"]

        client.put(f"/api/v1/plugins/ddw_chem_safety/hazard/{hazard_id}/status", json={
            "status": "整改中"
        })
        resp = client.put(f"/api/v1/plugins/ddw_chem_safety/hazard/{hazard_id}/status", json={  # noqa: E501
            "status": "已闭环",
            "resolution_note": "配电柜门已修复关闭"
        })
        assert resp.status_code == 200
        assert resp.json()["resolved_at"] is not None


# ═══════════════════════════════════════
# TC-7: 安全培训随机出题与答题
# ═══════════════════════════════════════


class TestTraining:

    def test_random_question_and_answer(self, client):
        resp = client.get("/api/v1/plugins/ddw_chem_safety/training/random-question")
        assert resp.status_code == 200
        q = resp.json()
        assert len(q["options"]) >= 2
        assert q["correct_index"] < len(q["options"])

        resp = client.post("/api/v1/plugins/ddw_chem_safety/training/answer", json={
            "question_id": q["id"],
            "selected_index": q["correct_index"]
        })
        assert resp.status_code == 200
        assert resp.json()["correct"] is True


# ═══════════════════════════════════════
# TC-8: 风险提示牌
# ═══════════════════════════════════════


class TestRiskBulletin:

    def test_hot_work_risk_bulletin(self, client):
        resp = client.get("/api/v1/plugins/ddw_chem_safety/risk-bulletin/hot_work")
        assert resp.status_code == 200
        data = resp.json()
        assert data["work_type"] == "动火作业"
        assert data["risk_level"] == "高风险"
        assert len(data["hazards"]) > 0
        assert len(data["control_measures"]) > 0
        assert len(data["emergency_procedures"]) > 0


# ═══════════════════════════════════════
# TC-9~13: 法规语料入库功能
# ═══════════════════════════════════════


class TestRegulations:

    def test_seed_regulations(self, client):
        """TC-9: 法规入库成功"""
        resp = client.post("/api/v1/plugins/ddw_chem_safety/regulations/seed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["inserted"] > 0
        assert data["total"] == data["inserted"] + data["skipped"]

    def test_seed_idempotent(self, client):
        """TC-10: 重复入库幂等，第二次全部 skipped"""
        client.post("/api/v1/plugins/ddw_chem_safety/regulations/seed")
        resp = client.post("/api/v1/plugins/ddw_chem_safety/regulations/seed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["inserted"] == 0
        assert data["skipped"] > 0

    def test_list_regulations(self, client):
        """TC-11: 法规列表不为空"""
        client.post("/api/v1/plugins/ddw_chem_safety/regulations/seed")
        resp = client.get("/api/v1/plugins/ddw_chem_safety/regulations")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) > 0
        assert any("安全生产法" in item["name"] for item in items)

    def test_get_regulation_detail(self, client):
        """TC-12: 法规详情包含完整条款"""
        client.post("/api/v1/plugins/ddw_chem_safety/regulations/seed")
        regs = client.get("/api/v1/plugins/ddw_chem_safety/regulations").json()
        reg_id = regs[0]["id"]
        resp = client.get(f"/api/v1/plugins/ddw_chem_safety/regulations/{reg_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == reg_id
        assert len(data["clauses"]) > 0
        assert len(data["applicable_scenarios"]) > 0

    def test_search_regulations_by_keyword(self, client):
        """TC-13: 关键词搜索命中法规"""
        client.post("/api/v1/plugins/ddw_chem_safety/regulations/seed")
        resp = client.get("/api/v1/plugins/ddw_chem_safety/regulations",
                          params={"keyword": "受限空间"})
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) > 0

    def test_get_nonexistent_regulation(self, client):
        """TC-14: 查询不存在的法规返回 404"""
        resp = client.get("/api/v1/plugins/ddw_chem_safety/regulations/99999")
        assert resp.status_code == 404

    def test_health_shows_regulation_count(self, client):
        """TC-15: 健康检查端点显示法规数量"""
        client.post("/api/v1/plugins/ddw_chem_safety/regulations/seed")
        resp = client.get("/api/v1/plugins/ddw_chem_safety/health")
        assert resp.status_code == 200
        assert resp.json()["regulation_count"] > 0
