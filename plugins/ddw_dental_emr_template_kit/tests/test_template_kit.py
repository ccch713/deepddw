"""ddw_dental_emr_template_kit 测试套件.

对齐 TASK_SPEC §T16:
  T16-1: 列出 9 个模板，type 不重复
  T16-2: extraction 模板 required_fields 含 anticoagulant_use
  T16-3: orthodontics 模板 required_fields 含 angle_class
  T16-4: 不存在的 type 返回 404
  T16-5: 所有 YAML 格式合法 (yaml.safe_load)
  T16-6: 每个模板至少 8 个字段
  T16-7: select 字段的 options 非空
"""
from __future__ import annotations

import conftest  # noqa: F401  # pylint: disable=unused-import
import pytest
import yaml
from plugins.ddw_dental_emr_template_kit import loader
from plugins.ddw_dental_emr_template_kit.router import router
from fastapi import FastAPI
from fastapi.testclient import TestClient

EXPECTED_TYPES = {
    "orthodontics", "pulp_open", "extraction", "cosmetic",
    "root_canal", "implant", "prosthesis", "periodontal", "pediatric",
}


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as c:
        yield c


# === T16-1: 列出 9 个模板，type 不重复 ===
def test_T16_1_list_9_unique_templates():
    items = loader.list_templates()
    assert len(items) == 9
    types = [it["type"] for it in items]
    assert len(set(types)) == 9
    assert set(types) == EXPECTED_TYPES


# === T16-2: extraction 模板 required_fields 含 anticoagulant_use ===
def test_T16_2_extraction_template_has_anticoagulant_use():
    tpl = loader.get_template_full("extraction")
    assert tpl is not None
    assert "anticoagulant_use" in tpl["required_fields"]
    assert "anticoagulant_use" in tpl["fields"]
    assert tpl["fields"]["anticoagulant_use"]["type"] == "boolean"


# === T16-3: orthodontics 模板 required_fields 含 angle_class ===
def test_T16_3_orthodontics_template_has_angle_class():
    tpl = loader.get_template_full("orthodontics")
    assert tpl is not None
    assert "angle_class" in tpl["required_fields"]
    assert "I" in tpl["fields"]["angle_class"]["options"]


# === T16-4: 不存在的 type 返回 404 ===
def test_T16_4_get_unknown_template_404(client):
    resp = client.get(
        "/api/v1/plugins/ddw_dental_emr_template_kit/templates/nonexistent_type_xxx"
    )
    assert resp.status_code == 404


# === T16-5: 所有 YAML 格式合法 ===
def test_T16_5_all_yaml_files_valid():
    for path in loader.list_template_files():
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert data is not None, f"{path} empty"
        assert "type" in data, f"{path} missing type"
        assert "fields" in data, f"{path} missing fields"


# === T16-6: 每个模板至少 8 个字段 ===
def test_T16_6_each_template_at_least_8_fields():
    for tt in EXPECTED_TYPES:
        tpl = loader.get_template_full(tt)
        assert tpl is not None, f"{tt} template not found"
        assert len(tpl.get("fields", {})) >= 8, f"{tt} has < 8 fields"
        assert len(tpl.get("required_fields", [])) >= 5, f"{tt} has < 5 required"


# === T16-7: select 字段的 options 非空 ===
def test_T16_7_select_options_not_empty():
    for tt in EXPECTED_TYPES:
        tpl = loader.get_template_full(tt)
        assert tpl is not None
        for fname, fdef in tpl.get("fields", {}).items():
            if fdef.get("type") == "select":
                opts = fdef.get("options")
                assert opts is not None, f"{tt}.{fname} select has no options"
                assert len(opts) > 0, f"{tt}.{fname} options empty"


# === 附加：health / list / validate ===
def test_extra_health(client):
    resp = client.get("/api/v1/plugins/ddw_dental_emr_template_kit/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["template_count"] == 9


def test_extra_list_endpoint(client):
    resp = client.get("/api/v1/plugins/ddw_dental_emr_template_kit/templates")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 9


def test_extra_get_extraction_full(client):
    resp = client.get(
        "/api/v1/plugins/ddw_dental_emr_template_kit/templates/extraction"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "extraction"
    assert "fields" in body
    assert "display_order" in body


def test_extra_validate_missing_fields(client):
    resp = client.post(
        "/api/v1/plugins/ddw_dental_emr_template_kit/templates/extraction/validate",
        json={"data": {"chief_complaint": "x"}},  # 其他必填缺失
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert len(body["missing"]) > 0


def test_extra_validate_full_data_valid(client):
    data = {
        "chief_complaint": "x", "present_illness": "y",
        "tooth_position": "左下8", "extraction_reason": "impaction",
        "difficulty_level": "surgical", "anesthesia_type": "local",
        "anticoagulant_use": False, "contraindications": "无",
        "postop_instructions": "咬棉球30分钟",
    }
    resp = client.post(
        "/api/v1/plugins/ddw_dental_emr_template_kit/templates/extraction/validate",
        json={"data": data},
    )
    body = resp.json()
    assert body["valid"] is True
    assert body["missing"] == []


def test_extra_validate_required_if(client):
    """anticoagulant_use=true 时 anticoagulant_drug 必填."""
    data = {
        "chief_complaint": "x", "present_illness": "y",
        "tooth_position": "左下8", "extraction_reason": "impaction",
        "difficulty_level": "surgical", "anesthesia_type": "local",
        "anticoagulant_use": True,
        "contraindications": "无", "postop_instructions": "z",
    }
    resp = client.post(
        "/api/v1/plugins/ddw_dental_emr_template_kit/templates/extraction/validate",
        json={"data": data},
    )
    body = resp.json()
    assert body["valid"] is False
    assert any(m["field"] == "anticoagulant_drug" for m in body["missing"])
