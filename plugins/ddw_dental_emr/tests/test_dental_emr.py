"""ddw_dental_emr 测试套件.

对齐 TASK_SPEC §T2:
  T2-1: 创建病历，返回 201 + id 非空
  T2-2: 获取病历，字段完整
  T2-3: 按 patient_id 查询列表，分页正确
  T2-4: 更新状态 draft → reviewed → finalized
  T2-5: from-transcript 端到端（mock T0+T1）
  T2-6: from-transcript 缺少 patient_id 返回 422
  T2-7: 查询不存在 record_id 返回 404
  T2-8: 牙周病历 special_findings 含 pd_values
  T2-9: 种植病历 special_findings 含 implant_brand
"""
from __future__ import annotations

import os

import conftest  # noqa: F401  # pylint: disable=unused-import

# mock 模式
os.environ["DDW_CLINICAL_ASR_MOCK"] = "1"
os.environ["DDW_TALK_A1_MOCK"] = "1"

import pytest
from plugins.ddw_dental_emr import router as plugin_router
from plugins.ddw_dental_emr.store import DentalRecordStore
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def app_instance(tmp_path, monkeypatch):
    db_path = tmp_path / "emr.db"
    store = DentalRecordStore(db_path=db_path)
    plugin_router.set_store(store)
    app = FastAPI()
    app.include_router(plugin_router.router)
    return app, store, db_path


@pytest.fixture()
def client(app_instance):
    app, _store, _db = app_instance
    with TestClient(app) as c:
        yield c


def _base_payload(**overrides):
    base = {
        "patient_id": "pt_001",
        "doctor_id": "doc_001",
        "treatment_type": "extraction",
        "chief_complaint": "左下8疼痛",
        "present_illness": "三天前开始疼痛",
        "diagnosis": "左下8阻生",
        "treatment_plan": "微创拔除",
    }
    base.update(overrides)
    return base


# === T2-1: 创建病历 ===
def test_T2_1_create_record_returns_201_with_id(client):
    resp = client.post("/api/v1/plugins/ddw_dental_emr/records", json=_base_payload())
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"]
    assert body["status"] == "draft"


# === T2-2: 获取病历字段完整 ===
def test_T2_2_get_record_full_fields(client):
    create_resp = client.post(
        "/api/v1/plugins/ddw_dental_emr/records", json=_base_payload()
    )
    rid = create_resp.json()["id"]
    resp = client.get(f"/api/v1/plugins/ddw_dental_emr/records/{rid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["patient_id"] == "pt_001"
    assert body["doctor_id"] == "doc_001"
    assert body["treatment_type"] == "extraction"
    assert body["chief_complaint"] == "左下8疼痛"


# === T2-3: 按 patient_id 查询 + 分页 ===
def test_T2_3_list_by_patient_with_pagination(client):
    for i in range(5):
        client.post(
            "/api/v1/plugins/ddw_dental_emr/records",
            json=_base_payload(patient_id=f"pt_{i:03d}"),
        )
    # pt_001 应该有 1 条
    resp = client.get(
        "/api/v1/plugins/ddw_dental_emr/records",
        params={"patient_id": "pt_001"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    # list all with pagination
    resp = client.get(
        "/api/v1/plugins/ddw_dental_emr/records",
        params={"page": 1, "page_size": 2},
    )
    assert resp.json()["total"] >= 5
    assert len(resp.json()["records"]) == 2


# === T2-4: 状态流转 draft → reviewed → finalized ===
def test_T2_4_status_transition(client):
    create_resp = client.post(
        "/api/v1/plugins/ddw_dental_emr/records", json=_base_payload()
    )
    rid = create_resp.json()["id"]
    for status in ("reviewed", "finalized"):
        resp = client.patch(
            f"/api/v1/plugins/ddw_dental_emr/records/{rid}/status",
            json={"status": status, "notes": f"已 {status}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == status


# === T2-5: from-transcript 端到端 ===
def test_T2_5_from_transcript_e2e(client):
    resp = client.post(
        "/api/v1/plugins/ddw_dental_emr/from-transcript",
        json={
            "transcript_job_id": "a1b2c3d4",
            "patient_id": "pt_001",
            "doctor_id": "doc_001",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["record"]["id"]
    assert body["record"]["transcript_job_id"] == "a1b2c3d4"
    assert "validation" in body


# === T2-6: from-transcript 缺少 patient_id 返回 400/422 ===
def test_T2_6_from_transcript_missing_patient(client):
    resp = client.post(
        "/api/v1/plugins/ddw_dental_emr/from-transcript",
        json={"transcript_job_id": "x", "doctor_id": "doc_001"},
    )
    assert resp.status_code in (400, 422)


# === T2-7: 不存在 record_id 404 ===
def test_T2_7_get_nonexistent_record_404(client):
    resp = client.get("/api/v1/plugins/ddw_dental_emr/records/nonexistent_xxx")
    assert resp.status_code == 404


# === T2-8: 牙周病历 special_findings ===
def test_T2_8_periodontal_special_findings(client):
    resp = client.post(
        "/api/v1/plugins/ddw_dental_emr/records",
        json=_base_payload(
            treatment_type="periodontal",
            special_findings={"pd_values": {"左上6": 5}, "bop_percentage": 35},
        ),
    )
    body = resp.json()
    assert body["treatment_type"] == "periodontal"
    assert "pd_values" in body["special_findings"]


# === T2-9: 种植病历 special_findings ===
def test_T2_9_implant_special_findings(client):
    resp = client.post(
        "/api/v1/plugins/ddw_dental_emr/records",
        json=_base_payload(
            treatment_type="implant",
            special_findings={
                "implant_brand": "Straumann",
                "implant_size": "4.1x10mm",
                "bone_quality": "II",
            },
        ),
    )
    body = resp.json()
    assert body["treatment_type"] == "implant"
    assert body["special_findings"]["implant_brand"] == "Straumann"


# === 附加：invalid treatment_type / health / templates ===
def test_extra_create_invalid_treatment_type(client):
    resp = client.post(
        "/api/v1/plugins/ddw_dental_emr/records",
        json=_base_payload(treatment_type="invalid_xxx"),
    )
    assert resp.status_code == 400


def test_extra_health(client):
    resp = client.get("/api/v1/plugins/ddw_dental_emr/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["template_count"] == 9


def test_extra_templates_proxy(client):
    resp = client.get("/api/v1/plugins/ddw_dental_emr/templates")
    assert resp.status_code == 200
    assert resp.json()["plugin"] == "ddw_dental_emr"


def test_extra_status_invalid(client):
    create_resp = client.post(
        "/api/v1/plugins/ddw_dental_emr/records", json=_base_payload()
    )
    rid = create_resp.json()["id"]
    resp = client.patch(
        f"/api/v1/plugins/ddw_dental_emr/records/{rid}/status",
        json={"status": "invalid_status"},
    )
    assert resp.status_code == 400


def test_extra_list_filter_by_doctor(client):
    client.post(
        "/api/v1/plugins/ddw_dental_emr/records",
        json=_base_payload(doctor_id="doc_001"),
    )
    client.post(
        "/api/v1/plugins/ddw_dental_emr/records",
        json=_base_payload(doctor_id="doc_002"),
    )
    resp = client.get(
        "/api/v1/plugins/ddw_dental_emr/records",
        params={"doctor_id": "doc_001"},
    )
    assert resp.json()["total"] >= 1
