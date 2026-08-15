"""ddw_offline_pos 测试套件.

对齐 TASK_SPEC §T5:
  T5-1: 创建收费记录，total_amount = sum(items.subtotal)
  T5-2: 确认收款，status → paid，paid_at 非空
  T5-3: 退款，status → refunded
  T5-4: 日结汇总按支付方式分组
  T5-5: 查询日期范围内记录
  T5-6: 收据号自动生成（R{YYYYMMDD}{seq}）
"""
from __future__ import annotations

from datetime import datetime, timezone

import conftest  # noqa: F401  # pylint: disable=unused-import
import pytest
from plugins.ddw_offline_pos import router as plugin_router
from plugins.ddw_offline_pos.store import PaymentStore
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def app_instance(tmp_path):
    db = tmp_path / "pay.db"
    store = PaymentStore(db_path=db)
    plugin_router.set_store(store)
    app = FastAPI()
    app.include_router(plugin_router.router)
    return app, store


@pytest.fixture()
def client(app_instance):
    app, _ = app_instance
    with TestClient(app) as c:
        yield c


def _payload(**over):
    base = {
        "patient_id": "pt_001",
        "doctor_id": "doc_001",
        "items": [
            {"item_name": "拔牙", "quantity": 1, "unit_price": 500.0, "subtotal": 500.0, "treatment_type": "extraction"},
            {"item_name": "麻药", "quantity": 1, "unit_price": 50.0, "subtotal": 50.0},
        ],
        "discount_amount": 0.0,
        "payment_method": "wechat",
    }
    base.update(over)
    return base


# === T5-1: 创建收费记录，total = sum(subtotal) ===
def test_T5_1_create_record_total_correct(client):
    resp = client.post("/api/v1/plugins/ddw_offline_pos/records", json=_payload())
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["total_amount"] == 550.0
    assert body["actual_amount"] == 550.0


# === T5-2: 确认收款，status → paid ===
def test_T5_2_mark_paid(client):
    rid = client.post(
        "/api/v1/plugins/ddw_offline_pos/records", json=_payload()
    ).json()["id"]
    resp = client.post(f"/api/v1/plugins/ddw_offline_pos/records/{rid}/pay")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "paid"
    assert body["paid_at"]


# === T5-3: 退款 ===
def test_T5_3_refund(client):
    rid = client.post(
        "/api/v1/plugins/ddw_offline_pos/records", json=_payload()
    ).json()["id"]
    client.post(f"/api/v1/plugins/ddw_offline_pos/records/{rid}/pay")
    resp = client.post(
        f"/api/v1/plugins/ddw_offline_pos/records/{rid}/refund",
        json={"refund_amount": 200.0, "reason": "患者取消"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "refunded"
    assert "refund=200" in body["notes"]


# === T5-4: 日结汇总按支付方式分组 ===
def test_T5_4_daily_summary_by_method(client):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # 创建 3 笔，分别 wechat/alipay/cash
    for m in ("wechat", "alipay", "cash"):
        rid = client.post(
            "/api/v1/plugins/ddw_offline_pos/records",
            json=_payload(payment_method=m),
        ).json()["id"]
        client.post(f"/api/v1/plugins/ddw_offline_pos/records/{rid}/pay")
    resp = client.get(
        "/api/v1/plugins/ddw_offline_pos/daily-summary",
        params={"date": today},
    )
    body = resp.json()
    assert body["total_income"] == 1650.0  # 3 * 550
    assert "wechat" in body["by_method"]
    assert "alipay" in body["by_method"]
    assert "cash" in body["by_method"]


# === T5-5: 日期范围查询 ===
def test_T5_5_filter_by_date(client):
    client.post("/api/v1/plugins/ddw_offline_pos/records", json=_payload())
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    resp = client.get(
        "/api/v1/plugins/ddw_offline_pos/records",
        params={"date": today},
    )
    assert resp.json()["total"] >= 1


# === T5-6: 收据号自动生成 ===
def test_T5_6_receipt_number_format(client):
    rid = client.post(
        "/api/v1/plugins/ddw_offline_pos/records", json=_payload()
    ).json()["id"]
    body = client.get(f"/api/v1/plugins/ddw_offline_pos/records/{rid}").json()
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    assert body["receipt_number"].startswith(f"R{today}")
    assert len(body["receipt_number"]) >= len(f"R{today}") + 1


# === 附加 ===
def test_extra_health(client):
    resp = client.get("/api/v1/plugins/ddw_offline_pos/health")
    assert resp.json()["status"] == "ok"


def test_extra_empty_items_400(client):
    resp = client.post(
        "/api/v1/plugins/ddw_offline_pos/records",
        json=_payload(items=[]),
    )
    assert resp.status_code == 400


def test_extra_invalid_method_400(client):
    resp = client.post(
        "/api/v1/plugins/ddw_offline_pos/records",
        json=_payload(payment_method="bitcoin"),
    )
    assert resp.status_code == 400


def test_extra_pay_twice_400(client):
    rid = client.post(
        "/api/v1/plugins/ddw_offline_pos/records", json=_payload()
    ).json()["id"]
    client.post(f"/api/v1/plugins/ddw_offline_pos/records/{rid}/pay")
    resp = client.post(f"/api/v1/plugins/ddw_offline_pos/records/{rid}/pay")
    assert resp.status_code == 400


def test_extra_refund_unpaid_400(client):
    rid = client.post(
        "/api/v1/plugins/ddw_offline_pos/records", json=_payload()
    ).json()["id"]
    resp = client.post(
        f"/api/v1/plugins/ddw_offline_pos/records/{rid}/refund",
        json={"refund_amount": 100.0},
    )
    assert resp.status_code == 400


def test_extra_refund_exceeds_400(client):
    rid = client.post(
        "/api/v1/plugins/ddw_offline_pos/records", json=_payload()
    ).json()["id"]
    client.post(f"/api/v1/plugins/ddw_offline_pos/records/{rid}/pay")
    resp = client.post(
        f"/api/v1/plugins/ddw_offline_pos/records/{rid}/refund",
        json={"refund_amount": 99999.0},
    )
    assert resp.status_code == 400


def test_extra_filter_by_patient(client):
    client.post(
        "/api/v1/plugins/ddw_offline_pos/records", json=_payload(patient_id="pt_A")
    )
    client.post(
        "/api/v1/plugins/ddw_offline_pos/records", json=_payload(patient_id="pt_B")
    )
    resp = client.get(
        "/api/v1/plugins/ddw_offline_pos/records",
        params={"patient_id": "pt_A"},
    )
    assert resp.json()["total"] >= 1


def test_extra_discount(client):
    resp = client.post(
        "/api/v1/plugins/ddw_offline_pos/records",
        json=_payload(discount_amount=50.0),
    )
    body = resp.json()
    assert body["actual_amount"] == 500.0
