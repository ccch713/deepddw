"""ddw_dental_sterilization 测试套件.

对齐 TASK_SPEC §T13:
  T13-1: 记录消毒批次, batch_number 唯一
  T13-2: 追溯: 输入 batch_id, 返回关联 patients
  T13-3: expiring 返回 7 天内过期
  T13-4: compliance 返回 pass_rate + failed
  T13-5: indicator_result=fail 标记异常
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import conftest  # noqa: F401  # pylint: disable=unused-import
import pytest
from plugins.ddw_dental_emr import router as emr_router
from plugins.ddw_dental_emr.store import DentalRecordStore
from plugins.ddw_dental_sterilization import router as plugin_router
from plugins.ddw_dental_sterilization.store import SterilizationStore
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def setup(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    ster = SterilizationStore(db_path=data / "sterilization.db")
    emr = DentalRecordStore(db_path=data / "dental_emr.db")
    plugin_router.set_store(ster)
    emr_router.set_store(emr)
    app = FastAPI()
    app.include_router(plugin_router.router)
    app.include_router(emr_router.router)
    return app, ster, emr


@pytest.fixture()
def client(setup):
    app, _, _ = setup
    with TestClient(app) as c:
        yield c


def _batch_payload(**over):
    base = {
        "batch_number": f"BT-{uuid.uuid4().hex[:6]}",
        "instruments": ["镊子1", "探针1"],
        "sterilizer_id": "ster_001",
        "cycle_type": "autoclave",
        "start_time": "2026-08-05T08:00:00Z",
        "end_time": "2026-08-05T08:30:00Z",
        "temperature": 134.0,
        "pressure": 2.1,
        "operator": "李护士",
        "expiry_date": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
    }
    base.update(over)
    return base


def _seed_sterilizer(client):
    return client.post(
        "/api/v1/plugins/ddw_dental_sterilization/sterilizers",
        json={"name": "高压锅 A"},
    ).json()["id"]


# === T13-1: batch_number 唯一 ===
def test_T13_1_batch_number_unique(client, setup):
    _app, _ster, _emr = setup
    ster_id = _seed_sterilizer(client)
    payload = _batch_payload(sterilizer_id=ster_id)
    r1 = client.post(
        "/api/v1/plugins/ddw_dental_sterilization/batches", json=payload
    )
    assert r1.status_code == 201
    # 重复 batch_number
    r2 = client.post(
        "/api/v1/plugins/ddw_dental_sterilization/batches", json=payload
    )
    assert r2.status_code in (400, 500)  # IntegrityError


# === T13-2: 追溯 batch → patients ===
def test_T13_2_trace_returns_patients(client, setup):
    _app, _ster, emr = setup
    ster_id = _seed_sterilizer(client)
    # 创建病历
    rec = emr.create({
        "patient_id": "pt_x", "doctor_id": "doc_001", "treatment_type": "extraction",
        "chief_complaint": "x", "present_illness": "y",
        "diagnosis": "z", "treatment_plan": "w",
    })
    bid = client.post(
        "/api/v1/plugins/ddw_dental_sterilization/batches",
        json=_batch_payload(sterilizer_id=ster_id, used_by_record_id=rec["id"]),
    ).json()["id"]
    resp = client.get(
        f"/api/v1/plugins/ddw_dental_sterilization/batches/{bid}/trace"
    )
    body = resp.json()
    assert "pt_x" in body["patients"]
    assert rec["id"] in body["record_ids"]


# === T13-3: expiring 7 天内 ===
def test_T13_3_expiring_7_days(client, setup):
    _app, _ster, _emr = setup
    ster_id = _seed_sterilizer(client)
    soon = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
    far = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    client.post(
        "/api/v1/plugins/ddw_dental_sterilization/batches",
        json=_batch_payload(sterilizer_id=ster_id, expiry_date=soon),
    )
    client.post(
        "/api/v1/plugins/ddw_dental_sterilization/batches",
        json=_batch_payload(sterilizer_id=ster_id, expiry_date=far),
    )
    resp = client.get("/api/v1/plugins/ddw_dental_sterilization/expiring")
    body = resp.json()
    assert body["total"] == 1


# === T13-4: compliance ===
def test_T13_4_compliance(client, setup):
    _app, _ster, _emr = setup
    ster_id = _seed_sterilizer(client)
    period = datetime.now().strftime("%Y-%m")
    for ok in (True, True, False):
        client.post(
            "/api/v1/plugins/ddw_dental_sterilization/batches",
            json=_batch_payload(
                sterilizer_id=ster_id,
                indicator_result="pass" if ok else "fail",
            ),
        )
    resp = client.get(
        "/api/v1/plugins/ddw_dental_sterilization/compliance",
        params={"period": period},
    )
    body = resp.json()
    assert body["total_batches"] >= 3
    assert body["failed_batches"] >= 1
    assert body["pass_rate"] < 1.0


# === T13-5: indicator_result=fail ===
def test_T13_5_indicator_fail(client, setup):
    _app, _ster, _emr = setup
    ster_id = _seed_sterilizer(client)
    r = client.post(
        "/api/v1/plugins/ddw_dental_sterilization/batches",
        json=_batch_payload(sterilizer_id=ster_id, indicator_result="fail"),
    )
    body = r.json()
    assert body["indicator_result"] == "fail"


# === 附加 ===
def test_extra_health(client):
    assert client.get("/api/v1/plugins/ddw_dental_sterilization/health").json()["status"] == "ok"


def test_extra_create_sterilizer(client):
    r = client.post(
        "/api/v1/plugins/ddw_dental_sterilization/sterilizers",
        json={"name": "X"},
    )
    assert r.status_code == 201


def test_extra_invalid_cycle_type_400(client, setup):
    _app, _ster, _emr = setup
    ster_id = _seed_sterilizer(client)
    r = client.post(
        "/api/v1/plugins/ddw_dental_sterilization/batches",
        json=_batch_payload(sterilizer_id=ster_id, cycle_type="invalid_xxx"),
    )
    assert r.status_code == 400


def test_extra_trace_404(client):
    resp = client.get(
        "/api/v1/plugins/ddw_dental_sterilization/batches/batch_xxx/trace"
    )
    assert resp.status_code == 404
