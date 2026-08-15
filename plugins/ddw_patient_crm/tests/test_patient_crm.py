"""ddw_patient_crm 测试套件.

对齐 TASK_SPEC §T3:
  T3-1: phone 唯一，重复 phone 返回 409
  T3-2: 按 name 模糊搜索
  T3-3: 按 phone 精确搜索
  T3-4: 按 tag 筛选
  T3-5: 获取患者就诊记录
  T3-6: stats 返回本月新增
  T3-7: 更新患者信息
  T3-8: patient → 病历 → 就诊记录（端到端）
"""
from __future__ import annotations

import uuid

import conftest  # noqa: F401  # pylint: disable=unused-import
import pytest
from plugins.ddw_dental_emr import router as emr_router
from plugins.ddw_dental_emr.store import DentalRecordStore
from plugins.ddw_patient_crm import router as plugin_router
from plugins.ddw_patient_crm.store import PatientStore
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def setup(tmp_path):
    """重定向 crm + emr 到同个 data 目录，便于跨插件关联."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    crm_store = PatientStore(db_path=data_dir / "patient_crm.db")
    emr_store = DentalRecordStore(db_path=data_dir / "dental_emr.db")
    plugin_router.set_store(crm_store)
    emr_router.set_store(emr_store)
    app = FastAPI()
    app.include_router(plugin_router.router)
    app.include_router(emr_router.router)
    return app, crm_store, emr_store, data_dir


@pytest.fixture()
def client(setup):
    app, _, _, _ = setup
    with TestClient(app) as c:
        yield c


def _phone():
    return f"13{uuid.uuid4().hex[:9]}"


def _patient_payload(**over):
    base = {
        "name": "张三",
        "phone": _phone(),
        "gender": "male",
        "source": "walk_in",
        "tags": ["VIP", "首次"],
        "allergies": ["青霉素"],
    }
    base.update(over)
    return base


# === T3-1: phone 唯一 ===
def test_T3_1_phone_unique_returns_409(client):
    phone = _phone()
    resp1 = client.post(
        "/api/v1/plugins/ddw_patient_crm/patients",
        json=_patient_payload(phone=phone),
    )
    assert resp1.status_code == 201
    resp2 = client.post(
        "/api/v1/plugins/ddw_patient_crm/patients",
        json=_patient_payload(phone=phone, name="李四"),
    )
    assert resp2.status_code == 409


# === T3-2: name 模糊搜索 ===
def test_T3_2_search_by_name_fuzzy(client):
    client.post("/api/v1/plugins/ddw_patient_crm/patients", json=_patient_payload(name="王晓明"))
    client.post("/api/v1/plugins/ddw_patient_crm/patients", json=_patient_payload(name="王晓东"))
    client.post("/api/v1/plugins/ddw_patient_crm/patients", json=_patient_payload(name="李四"))
    resp = client.get(
        "/api/v1/plugins/ddw_patient_crm/patients",
        params={"name": "王晓"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 2


# === T3-3: phone 精确搜索 ===
def test_T3_3_search_by_phone_exact(client):
    phone = _phone()
    client.post("/api/v1/plugins/ddw_patient_crm/patients", json=_patient_payload(phone=phone))
    resp = client.get(
        "/api/v1/plugins/ddw_patient_crm/patients",
        params={"phone": phone},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


# === T3-4: tag 筛选 ===
def test_T3_4_search_by_tag(client):
    client.post("/api/v1/plugins/ddw_patient_crm/patients", json=_patient_payload(tags=["VIP", "首次"]))
    client.post("/api/v1/plugins/ddw_patient_crm/patients", json=_patient_payload(tags=["普通"]))
    resp = client.get(
        "/api/v1/plugins/ddw_patient_crm/patients",
        params={"tag": "VIP"},
    )
    body = resp.json()
    assert body["total"] >= 1


# === T3-5: 获取患者就诊记录 ===
def test_T3_5_get_visits(client, setup):
    _app, _crm_store, emr_store, _ = setup
    p = client.post(
        "/api/v1/plugins/ddw_patient_crm/patients",
        json=_patient_payload(),
    ).json()
    pid = p["id"]
    emr_store.create({
        "patient_id": pid, "doctor_id": "doc_001", "treatment_type": "extraction",
        "chief_complaint": "x", "present_illness": "y", "diagnosis": "z", "treatment_plan": "w",
    })
    resp = client.get(f"/api/v1/plugins/ddw_patient_crm/patients/{pid}/visits")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert body["visits"][0]["treatment_type"] == "extraction"


# === T3-6: stats 返回本月新增 ===
def test_T3_6_stats_this_month(client):
    client.post("/api/v1/plugins/ddw_patient_crm/patients", json=_patient_payload())
    resp = client.get("/api/v1/plugins/ddw_patient_crm/stats")
    body = resp.json()
    assert body["total_patients"] >= 1
    assert body["this_month_new"] >= 1
    assert "by_source" in body
    assert "by_gender" in body


# === T3-7: 更新患者信息 ===
def test_T3_7_update_patient(client):
    p = client.post(
        "/api/v1/plugins/ddw_patient_crm/patients", json=_patient_payload()
    ).json()
    pid = p["id"]
    resp = client.patch(
        f"/api/v1/plugins/ddw_patient_crm/patients/{pid}",
        json={"name": "新名字", "notes": "已更新"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "新名字"
    assert body["notes"] == "已更新"


# === T3-8: 端到端 patient → 病历 → 就诊记录 ===
def test_T3_8_e2e_patient_to_visits(client, setup):
    _app, _crm, _emr, _ = setup
    p = client.post(
        "/api/v1/plugins/ddw_patient_crm/patients", json=_patient_payload()
    ).json()
    pid = p["id"]
    # 通过 EMR API 创建病历
    emr_resp = client.post(
        "/api/v1/plugins/ddw_dental_emr/records",
        json={
            "patient_id": pid, "doctor_id": "doc_001", "treatment_type": "extraction",
            "chief_complaint": "拔牙", "present_illness": "x", "diagnosis": "y", "treatment_plan": "z",
        },
    )
    assert emr_resp.status_code == 201
    # 通过 CRM 读就诊记录
    resp = client.get(f"/api/v1/plugins/ddw_patient_crm/patients/{pid}/visits")
    assert resp.json()["total"] >= 1


# === 附加 ===
def test_extra_health(client):
    resp = client.get("/api/v1/plugins/ddw_patient_crm/health")
    assert resp.json()["status"] == "ok"


def test_extra_get_404(client):
    resp = client.get("/api/v1/plugins/ddw_patient_crm/patients/pt_nonexistent_xxx")
    assert resp.status_code == 404


def test_extra_create_empty_name_400(client):
    resp = client.post(
        "/api/v1/plugins/ddw_patient_crm/patients",
        json={"name": "", "phone": _phone()},
    )
    assert resp.status_code == 400


def test_extra_create_invalid_source_400(client):
    resp = client.post(
        "/api/v1/plugins/ddw_patient_crm/patients",
        json={**_patient_payload(), "source": "invalid_source_xxx"},
    )
    assert resp.status_code == 400


def test_extra_visits_for_nonexistent_patient_404(client):
    resp = client.get(
        "/api/v1/plugins/ddw_patient_crm/patients/pt_nonexistent_xxx/visits"
    )
    assert resp.status_code == 404
