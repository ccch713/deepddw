"""ddw_commission 测试套件.

对齐 TASK_SPEC §T6:
  T6-1: 创建规则 extraction 15%, 计算 = income × 0.15
  T6-2: 同一医生多条收费, 提成合并
  T6-3: 多医生分别计算
  T6-4: 无匹配规则提成为 0
  T6-5: 确认提成 status → confirmed
  T6-6: min_amount 兜底
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import conftest  # noqa: F401  # pylint: disable=unused-import
import pytest
from plugins.ddw_commission import router as plugin_router
from plugins.ddw_commission.store import CommissionStore
from plugins.ddw_offline_pos import router as pay_router
from plugins.ddw_offline_pos.store import PaymentStore
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def setup(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    pay_store = PaymentStore(db_path=data_dir / "offline_pos.db")
    comm_store = CommissionStore(db_path=data_dir / "commission.db")
    pay_router.set_store(pay_store)
    plugin_router.set_store(comm_store)
    app = FastAPI()
    app.include_router(pay_router.router)
    app.include_router(plugin_router.router)
    return app, pay_store, comm_store, data_dir


@pytest.fixture()
def client(setup):
    app, _pay, _comm, _ = setup
    with TestClient(app) as c:
        yield c


def _seed_payment(client, doctor_id, items, period=None):
    """创建并支付一笔."""
    payload = {
        "patient_id": f"pt_{uuid.uuid4().hex[:6]}",
        "doctor_id": doctor_id,
        "items": items,
        "payment_method": "wechat",
    }
    rid = client.post(
        "/api/v1/plugins/ddw_offline_pos/records", json=payload
    ).json()["id"]
    client.post(f"/api/v1/plugins/ddw_offline_pos/records/{rid}/pay")
    return rid


# === T6-1: 规则 extraction 15% ===
def test_T6_1_extraction_15_percent(client, setup):
    _app, _pay, _comm, _ = setup
    # 制造当月数据
    today = datetime.now(timezone.utc).strftime("%Y-%m")
    _seed_payment(client, "doc_001", [
        {"item_name": "拔牙", "quantity": 1, "unit_price": 1000, "subtotal": 1000, "treatment_type": "extraction"}
    ])
    # 加规则
    client.post(
        "/api/v1/plugins/ddw_commission/rules",
        json={"treatment_type": "extraction", "percentage": 0.15},
    )
    # 计算
    resp = client.post(
        f"/api/v1/plugins/ddw_commission/calculate?period={today}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    record = next(r for r in body["records"] if r["doctor_id"] == "doc_001")
    assert record["total_income"] == 1000.0
    assert record["commission_amount"] == 150.0


# === T6-2: 同一医生多条收费提成合并 ===
def test_T6_2_merge_multiple_payments_same_doctor(client, setup):
    _app, _pay, _comm, _ = setup
    today = datetime.now(timezone.utc).strftime("%Y-%m")
    _seed_payment(client, "doc_001", [
        {"item_name": "x", "quantity": 1, "unit_price": 500, "subtotal": 500, "treatment_type": "extraction"}
    ])
    _seed_payment(client, "doc_001", [
        {"item_name": "y", "quantity": 1, "unit_price": 800, "subtotal": 800, "treatment_type": "extraction"}
    ])
    client.post(
        "/api/v1/plugins/ddw_commission/rules",
        json={"treatment_type": "extraction", "percentage": 0.10},
    )
    body = client.post(
        f"/api/v1/plugins/ddw_commission/calculate?period={today}"
    ).json()
    record = next(r for r in body["records"] if r["doctor_id"] == "doc_001")
    assert record["total_income"] == 1300.0
    assert record["commission_amount"] == 130.0


# === T6-3: 多医生分别计算 ===
def test_T6_3_multiple_doctors(client, setup):
    _app, _pay, _comm, _ = setup
    today = datetime.now(timezone.utc).strftime("%Y-%m")
    _seed_payment(client, "doc_001", [
        {"item_name": "x", "quantity": 1, "unit_price": 1000, "subtotal": 1000, "treatment_type": "extraction"}
    ])
    _seed_payment(client, "doc_002", [
        {"item_name": "y", "quantity": 1, "unit_price": 2000, "subtotal": 2000, "treatment_type": "implant"}
    ])
    client.post(
        "/api/v1/plugins/ddw_commission/rules",
        json={"treatment_type": "extraction", "percentage": 0.10},
    )
    client.post(
        "/api/v1/plugins/ddw_commission/rules",
        json={"treatment_type": "implant", "percentage": 0.05},
    )
    body = client.post(
        f"/api/v1/plugins/ddw_commission/calculate?period={today}"
    ).json()
    d1 = next(r for r in body["records"] if r["doctor_id"] == "doc_001")
    d2 = next(r for r in body["records"] if r["doctor_id"] == "doc_002")
    assert d1["commission_amount"] == 100.0
    assert d2["commission_amount"] == 100.0


# === T6-4: 无匹配规则提成为 0 ===
def test_T6_4_no_matching_rule_zero(client, setup):
    _app, _pay, _comm, _ = setup
    today = datetime.now(timezone.utc).strftime("%Y-%m")
    _seed_payment(client, "doc_001", [
        {"item_name": "x", "quantity": 1, "unit_price": 500, "subtotal": 500, "treatment_type": "extraction"}
    ])
    # 不加任何规则
    body = client.post(
        f"/api/v1/plugins/ddw_commission/calculate?period={today}"
    ).json()
    assert body["total"] == 0


# === T6-5: 确认提成 status → confirmed ===
def test_T6_5_confirm_record(client, setup):
    _app, _pay, _comm, _ = setup
    today = datetime.now(timezone.utc).strftime("%Y-%m")
    _seed_payment(client, "doc_001", [
        {"item_name": "x", "quantity": 1, "unit_price": 500, "subtotal": 500, "treatment_type": "extraction"}
    ])
    client.post(
        "/api/v1/plugins/ddw_commission/rules",
        json={"treatment_type": "extraction", "percentage": 0.10},
    )
    client.post(f"/api/v1/plugins/ddw_commission/calculate?period={today}")
    rid = client.get(
        "/api/v1/plugins/ddw_commission/records",
        params={"period": today},
    ).json()["records"][0]["id"]
    resp = client.post(
        f"/api/v1/plugins/ddw_commission/records/{rid}/confirm"
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"


# === T6-6: min_amount 兜底 ===
def test_T6_6_min_amount_floor(client, setup):
    _app, _pay, _comm, _ = setup
    today = datetime.now(timezone.utc).strftime("%Y-%m")
    _seed_payment(client, "doc_001", [
        {"item_name": "x", "quantity": 1, "unit_price": 100, "subtotal": 100, "treatment_type": "extraction"}
    ])
    client.post(
        "/api/v1/plugins/ddw_commission/rules",
        json={"treatment_type": "extraction", "percentage": 0.05, "min_amount": 50.0},
    )
    body = client.post(
        f"/api/v1/plugins/ddw_commission/calculate?period={today}"
    ).json()
    record = body["records"][0]
    # 100 * 0.05 = 5 < 50, 兜底 50
    assert record["commission_amount"] == 50.0


# === 附加 ===
def test_extra_health(client):
    resp = client.get("/api/v1/plugins/ddw_commission/health")
    assert resp.json()["status"] == "ok"


def test_extra_create_rule_invalid_pct(client):
    resp = client.post(
        "/api/v1/plugins/ddw_commission/rules",
        json={"treatment_type": "extraction", "percentage": 1.5},
    )
    assert resp.status_code == 400


def test_extra_calculate_invalid_period(client):
    resp = client.post("/api/v1/plugins/ddw_commission/calculate?period=2026")
    assert resp.status_code == 400


def test_extra_confirm_404(client):
    resp = client.post(
        "/api/v1/plugins/ddw_commission/records/cr_xxx/confirm"
    )
    assert resp.status_code == 404


def test_extra_general_rule_applies_to_all(client, setup):
    _app, _pay, _comm, _ = setup
    today = datetime.now(timezone.utc).strftime("%Y-%m")
    _seed_payment(client, "doc_001", [
        {"item_name": "x", "quantity": 1, "unit_price": 1000, "subtotal": 1000, "treatment_type": "unknown_tt"}
    ])
    client.post(
        "/api/v1/plugins/ddw_commission/rules",
        json={"treatment_type": "general", "percentage": 0.05},
    )
    body = client.post(
        f"/api/v1/plugins/ddw_commission/calculate?period={today}"
    ).json()
    record = next(r for r in body["records"] if r["doctor_id"] == "doc_001")
    assert record["commission_amount"] == 50.0
