"""ddw_aggregated_pay 测试套件.

对齐 TASK_SPEC §T15:
  T15-1: 创建微信支付, status=pending
  T15-2: 查询支付状态
  T15-3: 对账: 匹配成功 + 未匹配分别列出
  T15-4: 对账报告含 mismatched 列表
  T15-5: 多通道并行对账
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import conftest  # noqa: F401  # pylint: disable=unused-import
import pytest
from ddw_aggregated_pay import router as plugin_router
from ddw_aggregated_pay.store import AggregatedPayStore
from ddw_payment import router as pay_router
from ddw_payment.store import PaymentStore
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def setup(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    pay = PaymentStore(db_path=data / "payment.db")
    agg = AggregatedPayStore(db_path=data / "aggregated_pay.db")
    pay_router.set_store(pay)
    plugin_router.set_store(agg)
    app = FastAPI()
    app.include_router(pay_router.router)
    app.include_router(plugin_router.router)
    return app, pay, agg


@pytest.fixture()
def client(setup):
    app, _, _ = setup
    with TestClient(app) as c:
        yield c


def _seed_paid(client, amount=500.0):
    payload = {
        "patient_id": f"pt_{uuid.uuid4().hex[:6]}",
        "doctor_id": "doc_001",
        "items": [{"item_name": "x", "unit_price": amount, "subtotal": amount, "quantity": 1, "treatment_type": "extraction"}],  # noqa: E501
        "payment_method": "wechat",
        "total_amount": amount,
        "actual_amount": amount,
    }
    rid = client.post(
        "/api/v1/plugins/ddw_payment/records", json=payload
    ).json()["id"]
    client.post(f"/api/v1/plugins/ddw_payment/records/{rid}/pay")
    return rid


# === T15-1: 创建微信支付, status=pending ===
def test_T15_1_create_wechat_payment_pending(client):
    r = client.post(
        "/api/v1/plugins/ddw_aggregated_pay/transactions",
        json={"payment_record_id": "pay_001", "channel": "wechat_pay", "amount": 500.0},
    )
    assert r.status_code == 201
    assert r.json()["status"] == "pending"


# === T15-2: 查询支付状态 ===
def test_T15_2_query_status(client):
    r = client.post(
        "/api/v1/plugins/ddw_aggregated_pay/transactions",
        json={"payment_record_id": "pay_001", "channel": "wechat_pay", "amount": 500.0},
    )
    tid = r.json()["id"]
    resp = client.get(f"/api/v1/plugins/ddw_aggregated_pay/transactions/{tid}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


# === T15-3: 对账匹配 + 不匹配 ===
def test_T15_3_reconcile_matched_and_mismatched(client, setup):
    _app, _pay, _agg = setup
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # 创建 1 笔 paid 支付
    paid_id = _seed_paid(client, 500.0)
    # 创建对应 success 交易
    client.post(
        "/api/v1/plugins/ddw_aggregated_pay/transactions",
        json={"payment_record_id": paid_id, "channel": "wechat_pay", "amount": 500.0},
    )
    tid = client.get(
        "/api/v1/plugins/ddw_aggregated_pay/transactions",
        params={"status": "pending"},
    ).json()["transactions"][0]["id"]
    client.patch(
        f"/api/v1/plugins/ddw_aggregated_pay/transactions/{tid}",
        json={"status": "success", "trade_no": "wx_12345"},
    )
    # 触发对账
    resp = client.post(
        f"/api/v1/plugins/ddw_aggregated_pay/reconcile?date={today}"
    )
    body = resp.json()
    assert body["matched"] >= 1
    assert body["diff"] == 0


# === T15-4: 对账报告含 mismatched ===
def test_T15_4_reconcile_report_has_mismatched(client):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # 创建 paid 支付但无对应交易
    _seed_paid(client, 200.0)
    resp = client.get(
        "/api/v1/plugins/ddw_aggregated_pay/reconcile-report",
        params={"date": today},
    )
    body = resp.json()
    # 至少有 1 个未匹配
    assert any(
        m["reason"] and "无对应" in m["reason"]
        for m in body["mismatched"]
    )


# === T15-5: 多通道并行对账 ===
def test_T15_5_multi_channel_reconcile(client, setup):
    _app, _pay, _agg = setup
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rid1 = _seed_paid(client, 300.0)
    rid2 = _seed_paid(client, 400.0)
    # 不同通道
    for rid, ch in [(rid1, "wechat_pay"), (rid2, "alipay")]:
        r = client.post(
            "/api/v1/plugins/ddw_aggregated_pay/transactions",
            json={"payment_record_id": rid, "channel": ch,
                "amount": 300.0 if ch == "wechat_pay" else 400.0},
        )
        tid = r.json()["id"]
        client.patch(
            f"/api/v1/plugins/ddw_aggregated_pay/transactions/{tid}",
            json={"status": "success"},
        )
    resp = client.post(
        f"/api/v1/plugins/ddw_aggregated_pay/reconcile?date={today}"
    )
    body = resp.json()
    assert body["matched"] >= 2
    assert body["payment_total"] >= 700.0
    assert body["transaction_total"] >= 700.0


# === 附加 ===
def test_extra_health(client):
    assert client.get(
        "/api/v1/plugins/ddw_aggregated_pay/health"
    ).json()["status"] == "ok"


def test_extra_create_channel(client):
    r = client.post(
        "/api/v1/plugins/ddw_aggregated_pay/channels",
        json={"channel_name": "wechat_pay"},
    )
    assert r.status_code == 201
    assert r.json()["channel_name"] == "wechat_pay"


def test_extra_list_channels(client):
    client.post(
        "/api/v1/plugins/ddw_aggregated_pay/channels",
        json={"channel_name": "alipay"},
    )
    resp = client.get("/api/v1/plugins/ddw_aggregated_pay/channels")
    body = resp.json()
    assert body["total"] >= 1


def test_extra_create_tx_invalid_status(client):
    r = client.post(
        "/api/v1/plugins/ddw_aggregated_pay/transactions",
        json={"payment_record_id": "x", "channel": "wechat", "amount": 100.0},
    )
    assert r.status_code == 201  # 默认 pending
    tid = r.json()["id"]
    # 更新为 invalid status
    r2 = client.patch(
        f"/api/v1/plugins/ddw_aggregated_pay/transactions/{tid}",
        json={"status": "invalid_xxx"},
    )
    assert r2.status_code == 400


def test_extra_get_404(client):
    r = client.get(
        "/api/v1/plugins/ddw_aggregated_pay/transactions/ptx_xxx"
    )
    assert r.status_code == 404
