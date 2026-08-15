"""M2 Router 层冒烟测试（TestClient，零 500）。"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.ddw_wallet.router import build_router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(build_router())
    return TestClient(app)


def test_health(client):
    """GET /health 200。"""
    resp = client.get("/api/v1/plugins/ddw_wallet/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_create_account(client):
    """POST /accounts 200。"""
    resp = client.post("/api/v1/plugins/ddw_wallet/accounts?user_id=u_smoke1&tenant_id=default")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "u_smoke1"
    assert "recharge_balance_cents" in data


def test_get_account(client):
    """GET /accounts/{uid} 200。"""
    client.post("/api/v1/plugins/ddw_wallet/accounts?user_id=u_smoke2&tenant_id=default")
    resp = client.get("/api/v1/plugins/ddw_wallet/accounts/u_smoke2?tenant_id=default")
    assert resp.status_code == 200


def test_get_account_not_found(client):
    """GET /accounts/{uid} 404。"""
    resp = client.get("/api/v1/plugins/ddw_wallet/accounts/nonexist?tenant_id=default")
    assert resp.status_code == 404


def test_recharge_options(client):
    """POST /recharges 422（缺字段）。"""
    resp = client.post("/api/v1/plugins/ddw_wallet/recharges", json={})
    assert resp.status_code == 422


def test_charges_422(client):
    """POST /charges 422（缺字段）。"""
    resp = client.post("/api/v1/plugins/ddw_wallet/charges", json={})
    assert resp.status_code == 422


def test_refunds_422(client):
    """POST /refunds 422（缺字段）。"""
    resp = client.post("/api/v1/plugins/ddw_wallet/refunds", json={})
    assert resp.status_code == 422


def test_transactions(client):
    """GET /transactions 200。"""
    resp = client.get("/api/v1/plugins/ddw_wallet/transactions?user_id=u_smoke1&tenant_id=default")
    assert resp.status_code == 200


def test_rates(client):
    """GET /rates 200。"""
    resp = client.get("/api/v1/plugins/ddw_wallet/rates")
    assert resp.status_code == 200


def test_audit_logs(client):
    """GET /audit-logs 200。"""
    resp = client.get("/api/v1/plugins/ddw_wallet/audit-logs?tenant_id=default")
    assert resp.status_code == 200


def test_platform_accounts(client):
    """GET /platform/accounts 200。"""
    resp = client.get("/api/v1/plugins/ddw_wallet/platform/accounts?tenant_id=default")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_fee_cents" in data


def test_reconcile(client):
    """POST /reconcile 200。"""
    resp = client.post("/api/v1/plugins/ddw_wallet/reconcile", json={"date": "2026-08-12"})
    assert resp.status_code == 200


def test_reconcile_report(client):
    """GET /reconcile/report 200。"""
    resp = client.get("/api/v1/plugins/ddw_wallet/reconcile/report?date=2026-08-12")
    assert resp.status_code == 200


def test_freeze_422(client):
    """POST /accounts/{uid}/freeze 422（缺字段）。"""
    resp = client.post("/api/v1/plugins/ddw_wallet/accounts/u_smoke1/freeze", json={})
    assert resp.status_code == 422


def test_withdraw_422(client):
    """POST /withdraw 422（缺字段）。"""
    resp = client.post("/api/v1/plugins/ddw_wallet/withdraw", json={})
    assert resp.status_code == 422


def test_notify_alipay_no_500(client):
    """POST /recharges/notify/alipay 空 body → 严禁 500（SDK 未装时 200 FAIL 也可）。"""
    resp = client.post(
        "/api/v1/plugins/ddw_wallet/recharges/notify/alipay",
        content=b"",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code in (200, 400, 402)


def test_notify_wechat_no_500(client):
    """POST /recharges/notify/wechat 空 body → 严禁 500（SDK 未装时 200 FAIL 也可）。"""
    resp = client.post(
        "/api/v1/plugins/ddw_wallet/recharges/notify/wechat",
        content=b"{}",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code in (200, 400, 402)
