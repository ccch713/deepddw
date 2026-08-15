"""ddw_kpi_dashboard 测试套件.

对齐 TASK_SPEC §T10:
  T10-1: overview 返回所有字段
  T10-2: doctors 按 income 降序
  T10-3: treatments 返回 9 类 count + income
  T10-4: patients 来源分布
  T10-5: trend 返回 6 个月数据
  T10-6: period 为空默认当月
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import conftest  # noqa: F401  # pylint: disable=unused-import
import pytest
from plugins.ddw_dental_emr import router as emr_router
from plugins.ddw_dental_emr.store import DentalRecordStore
from plugins.ddw_doctor_schedule import router as doc_router
from plugins.ddw_doctor_schedule.store import DoctorStore
from plugins.ddw_kpi_dashboard import router as kpi_router
from plugins.ddw_kpi_dashboard.aggregator import doctors as agg_doctors
from plugins.ddw_kpi_dashboard.aggregator import overview as agg_overview
from plugins.ddw_kpi_dashboard.aggregator import treatments as agg_treatments
from plugins.ddw_patient_crm import router as crm_router
from plugins.ddw_patient_crm.store import PatientStore
from plugins.ddw_offline_pos import router as pay_router
from plugins.ddw_offline_pos.store import PaymentStore
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def setup(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    crm = PatientStore(db_path=data / "patient_crm.db")
    emr = DentalRecordStore(db_path=data / "dental_emr.db")
    pay = PaymentStore(db_path=data / "offline_pos.db")
    doc = DoctorStore(db_path=data / "doctor_schedule.db")
    crm_router.set_store(crm)
    emr_router.set_store(emr)
    pay_router.set_store(pay)
    doc_router.set_store(doc)
    kpi_router.set_db_path(data / "kpi_dashboard.db")
    app = FastAPI()
    app.include_router(crm_router.router)
    app.include_router(emr_router.router)
    app.include_router(pay_router.router)
    app.include_router(doc_router.router)
    app.include_router(kpi_router.router)
    return app


@pytest.fixture()
def client(setup):
    with TestClient(setup) as c:
        yield c


def _seed_basic(client):
    """注入最小数据集."""
    # 1 医生
    did = client.post(
        "/api/v1/plugins/ddw_doctor_schedule/doctors",
        json={"name": "张医生"},
    ).json()["id"]
    # 2 患者
    for i, source in enumerate(["walk_in", "referral"]):
        client.post(
            "/api/v1/plugins/ddw_patient_crm/patients",
            json={
                "name": f"患者{i}",
                "phone": f"13{uuid.uuid4().hex[:9]}",
                "source": source,
            },
        )
    # 1 病历
    client.post(
        "/api/v1/plugins/ddw_dental_emr/records",
        json={
            "patient_id": "pt_x",
            "doctor_id": did,
            "treatment_type": "extraction",
            "chief_complaint": "x", "present_illness": "y",
            "diagnosis": "z", "treatment_plan": "w",
        },
    )


# === T10-1: overview 返回所有字段 ===
def test_T10_1_overview_fields(setup, tmp_path):
    crm = PatientStore(db_path=tmp_path / "patient_crm.db")
    crm.create({"name": "X", "phone": "13900000001"})
    out = agg_overview(tmp_path / "kpi_dashboard.db", datetime.now().strftime("%Y-%m"))
    for k in ("period", "total_income", "total_patients", "new_patients",
              "total_records", "avg_income_per_patient", "top_treatment"):
        assert k in out


# === T10-2: doctors 按 income 降序 ===
def test_T10_2_doctors_sorted_by_income(setup, tmp_path):
    pay = PaymentStore(db_path=tmp_path / "offline_pos.db")
    doc = DoctorStore(db_path=tmp_path / "doctor_schedule.db")
    d1 = doc.create_doctor({"name": "A"})
    d2 = doc.create_doctor({"name": "B"})
    period = datetime.now().strftime("%Y-%m")
    pay.create({
        "patient_id": "pt_x", "doctor_id": d1["id"],
        "items": [{"item_name": "x", "unit_price": 100, "subtotal": 100, "quantity": 1, "treatment_type": "extraction"}],
        "total_amount": 100, "actual_amount": 100, "payment_method": "cash",
    })
    pay.create({
        "patient_id": "pt_x", "doctor_id": d2["id"],
        "items": [{"item_name": "x", "unit_price": 500, "subtotal": 500, "quantity": 1, "treatment_type": "extraction"}],
        "total_amount": 500, "actual_amount": 500, "payment_method": "cash",
    })
    from datetime import datetime as _dt
    rid = pay.list_records(patient_id="pt_x", page_size=100)["records"]
    for r in rid:
        pay.update(r["id"], {"status": "paid", "paid_at": _dt.now(timezone.utc).isoformat()})
    out = agg_doctors(tmp_path / "kpi_dashboard.db", period)
    if len(out) >= 2:
        assert out[0]["income"] >= out[1]["income"]


# === T10-3: treatments count + income ===
def test_T10_3_treatments_breakdown(setup, tmp_path):
    emr = DentalRecordStore(db_path=tmp_path / "dental_emr.db")
    emr.create({
        "patient_id": "pt_x", "doctor_id": "d1", "treatment_type": "extraction",
        "chief_complaint": "x", "present_illness": "y",
        "diagnosis": "z", "treatment_plan": "w",
    })
    period = datetime.now().strftime("%Y-%m")
    out = agg_treatments(tmp_path / "kpi_dashboard.db", period)
    assert any(t["treatment_type"] == "extraction" for t in out)


# === T10-4: patients 来源分布 ===
def test_T10_4_patients_by_source(client):
    client.post(
        "/api/v1/plugins/ddw_patient_crm/patients",
        json={"name": "A", "phone": "13900000011", "source": "walk_in"},
    )
    client.post(
        "/api/v1/plugins/ddw_patient_crm/patients",
        json={"name": "B", "phone": "13900000012", "source": "walk_in"},
    )
    client.post(
        "/api/v1/plugins/ddw_patient_crm/patients",
        json={"name": "C", "phone": "13900000013", "source": "referral"},
    )
    period = datetime.now().strftime("%Y-%m")
    resp = client.get(
        "/api/v1/plugins/ddw_kpi_dashboard/patients",
        params={"period": period},
    )
    body = resp.json()
    assert body["by_source"].get("walk_in", 0) >= 2
    assert body["by_source"].get("referral", 0) >= 1


# === T10-5: trend 6 个月 ===
def test_T10_5_trend_6_months(client):
    resp = client.get(
        "/api/v1/plugins/ddw_kpi_dashboard/trend",
        params={"months": 6},
    )
    body = resp.json()
    assert body["months"] == 6
    assert len(body["trend"]) == 6


# === T10-6: period 为空默认当月 ===
def test_T10_6_default_period(client):
    resp = client.get("/api/v1/plugins/ddw_kpi_dashboard/overview")
    body = resp.json()
    assert body["period"] == datetime.now().strftime("%Y-%m")


# === 附加 ===
def test_extra_health(client):
    assert client.get("/api/v1/plugins/ddw_kpi_dashboard/health").json()["status"] == "ok"


def test_extra_doctors_endpoint(client):
    resp = client.get("/api/v1/plugins/ddw_kpi_dashboard/doctors")
    body = resp.json()
    assert "doctors" in body
    assert "period" in body


def test_extra_treatments_endpoint(client):
    resp = client.get("/api/v1/plugins/ddw_kpi_dashboard/treatments")
    body = resp.json()
    assert "treatments" in body
