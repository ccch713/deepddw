"""Tests for ddw-esg-payment plugin."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

# Modules pre-loaded by conftest.py via importlib.util
import plugins.ddw_esg_payment as ddw_esg_payment
import pytest
from plugins.ddw_esg_payment.models import Order
from plugins.ddw_esg_payment.promo import (
    PROMO_CONFIG,
    calculate_commission,
    generate_promo_code,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

router = ddw_esg_payment.router
register = ddw_esg_payment.register

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    app = FastAPI()
    register(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_health_check(client):
    resp = client.get("/api/v1/plugins/ddw-esg-payment/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["plugin"] == "ddw-esg-payment"


def test_create_order(client):
    resp = client.post(
        "/api/v1/plugins/ddw-esg-payment/orders",
        json={"user_id": "u1", "plan_id": "single", "pay_method": "wechat"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "u1"
    assert data["plan_id"] == "single"
    assert data["original_amount"] == 990
    assert data["final_amount"] == 990
    assert data["status"] == "pending"
    assert data["trade_no"] is not None


def test_create_order_with_coupon(client):
    # First create an order to get the welcome coupon
    resp = client.post(
        "/api/v1/plugins/ddw-esg-payment/orders",
        json={"user_id": "u2", "plan_id": "single"},
    )
    assert resp.status_code == 200

    # Get welcome coupon
    resp = client.get(
        "/api/v1/plugins/ddw-esg-payment/coupons/my",
        params={"user_id": "u2"},
    )
    coupons = resp.json()
    assert len(coupons) >= 1
    coupon_id = coupons[0]["id"]

    # Create order with coupon
    resp = client.post(
        "/api/v1/plugins/ddw-esg-payment/orders",
        json={"user_id": "u2", "plan_id": "single", "coupon_id": coupon_id},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["coupon_amount"] == PROMO_CONFIG["coupon_amounts"]["welcome"]
    assert data["final_amount"] == max(0, 990 - PROMO_CONFIG["coupon_amounts"]["welcome"])


def test_wechat_payment(client):
    resp = client.post(
        "/api/v1/plugins/ddw-esg-payment/orders",
        json={"user_id": "u3", "plan_id": "single"},
    )
    order_id = resp.json()["id"]

    resp = client.post(
        "/api/v1/plugins/ddw-esg-payment/pay/wechat/create",
        params={"order_id": order_id},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "prepay_id" in data
    assert data["prepay_id"].startswith("wx_demo_")


def test_alipay_payment(client):
    resp = client.post(
        "/api/v1/plugins/ddw-esg-payment/orders",
        json={"user_id": "u4", "plan_id": "single"},
    )
    order_id = resp.json()["id"]

    resp = client.post(
        "/api/v1/plugins/ddw-esg-payment/pay/alipay/create",
        params={"order_id": order_id},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "qr_code" in data
    assert "alipay.com" in data["qr_code"]


def test_generate_promo_code():
    code = generate_promo_code("HY")
    assert len(code) == 9
    assert code.startswith("HY")
    assert code[-1].isdigit()

    code2 = generate_promo_code("VIP")
    assert code2.startswith("VIP")


def test_commission_calculation():
    comm, rate = calculate_commission(990, 10)
    assert comm == int(990 * 0.30)
    assert rate == 0.30

    comm, rate = calculate_commission(199900, 10)
    assert comm == int(199900 * 0.35)
    assert rate == 0.35


def test_commission_cold_start():
    comm, rate = calculate_commission(990, 3)
    assert rate == 0.35
    assert comm == int(990 * 0.35)

    comm2, rate2 = calculate_commission(990, 6)
    assert rate2 == 0.30
    assert comm2 == int(990 * 0.30)


def test_webhook_idempotent(client, monkeypatch):
    """安全修复后：配置签名密钥 + 正确签名 → 200（幂等）；无密钥/错签名 → 401。"""
    import hashlib
    import hmac

    monkeypatch.setenv("DDW_ESG_PAYMENT_WEBHOOK_SECRET", "test-webhook-secret")
    payload = b'{"test": true}'
    sig = hmac.new(b"test-webhook-secret", payload, hashlib.sha256).hexdigest()
    headers = {"signature": sig, "content-type": "application/json"}

    resp = client.post(
        "/api/v1/plugins/ddw-esg-payment/webhook/wechat",
        content=payload,
        headers=headers,
    )
    assert resp.status_code == 200

    resp2 = client.post(
        "/api/v1/plugins/ddw-esg-payment/webhook/wechat",
        content=payload,
        headers=headers,
    )
    assert resp2.status_code == 200


def test_order_expiry():
    now = datetime.now()
    order = Order(
        id=str(uuid.uuid4()),
        user_id="u5",
        plan_id="single",
        original_amount=990,
        final_amount=990,
        status="pending",
        created_at=now - timedelta(minutes=31),
    )
    assert order.status == "pending"
    assert order.created_at is not None
    elapsed = (now - order.created_at).total_seconds() / 60
    assert elapsed > 30
