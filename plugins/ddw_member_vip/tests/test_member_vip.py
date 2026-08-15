"""ddw_member_vip 测试套件.

对齐 TASK_SPEC §T9:
  T9-1: 充值 500, 余额 = 550, level → silver
  T9-2: 消费 100, 余额 = 450
  T9-3: 余额不足时消费 400
  T9-4: 充值 2000, level → gold, discount_rate → 0.9
  T9-5: 交易记录按时间倒序
  T9-6: stats 返回总储值/总消费/会员数/等级分布
  T9-7: 同一 patient_id 不能创建两个 account (409)
"""
from __future__ import annotations

import conftest  # noqa: F401  # pylint: disable=unused-import
import pytest
from plugins.ddw_member_vip import router as plugin_router
from plugins.ddw_member_vip.store import MemberStore
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def app_instance(tmp_path):
    db = tmp_path / "vip.db"
    store = MemberStore(db_path=db)
    plugin_router.set_store(store)
    app = FastAPI()
    app.include_router(plugin_router.router)
    return app, store


@pytest.fixture()
def client(app_instance):
    app, _ = app_instance
    with TestClient(app) as c:
        yield c


# === T9-1: 充值 500, 余额 = 550, level silver ===
def test_T9_1_recharge_500_with_gift_to_silver(client):
    aid = client.post(
        "/api/v1/plugins/ddw_member_vip/accounts",
        json={"patient_id": "pt_001"},
    ).json()["id"]
    r = client.post(
        f"/api/v1/plugins/ddw_member_vip/accounts/{aid}/recharge",
        json={"amount": 500.0, "description": "首次充值"},
    )
    body = r.json()
    assert body["balance"] == 550.0  # 500 + 50 赠送
    assert body["level"] == "silver"
    assert body["discount_rate"] == 0.95


# === T9-2: 消费 100, 余额 = 450 ===
def test_T9_2_consume_100(client):
    aid = client.post(
        "/api/v1/plugins/ddw_member_vip/accounts",
        json={"patient_id": "pt_002"},
    ).json()["id"]
    client.post(
        f"/api/v1/plugins/ddw_member_vip/accounts/{aid}/recharge",
        json={"amount": 500.0},
    )
    r = client.post(
        f"/api/v1/plugins/ddw_member_vip/accounts/{aid}/consume",
        json={"amount": 100.0, "description": "拔牙"},
    )
    body = r.json()
    assert body["balance"] == 450.0


# === T9-3: 余额不足时消费 400 ===
def test_T9_3_consume_over_balance_400(client):
    aid = client.post(
        "/api/v1/plugins/ddw_member_vip/accounts",
        json={"patient_id": "pt_003"},
    ).json()["id"]
    r = client.post(
        f"/api/v1/plugins/ddw_member_vip/accounts/{aid}/consume",
        json={"amount": 100.0},
    )
    assert r.status_code == 400
    assert "不足" in r.json()["detail"]


# === T9-4: 充值 2000, level gold, discount 0.9 ===
def test_T9_4_recharge_2000_to_gold(client):
    aid = client.post(
        "/api/v1/plugins/ddw_member_vip/accounts",
        json={"patient_id": "pt_004"},
    ).json()["id"]
    r = client.post(
        f"/api/v1/plugins/ddw_member_vip/accounts/{aid}/recharge",
        json={"amount": 2000.0},
    )
    body = r.json()
    assert body["level"] == "gold"
    assert body["discount_rate"] == 0.9


# === T9-5: 交易记录按时间倒序 ===
def test_T9_5_transactions_descending(client):
    aid = client.post(
        "/api/v1/plugins/ddw_member_vip/accounts",
        json={"patient_id": "pt_005"},
    ).json()["id"]
    client.post(
        f"/api/v1/plugins/ddw_member_vip/accounts/{aid}/recharge",
        json={"amount": 100.0},
    )
    client.post(
        f"/api/v1/plugins/ddw_member_vip/accounts/{aid}/consume",
        json={"amount": 30.0},
    )
    client.post(
        f"/api/v1/plugins/ddw_member_vip/accounts/{aid}/recharge",
        json={"amount": 50.0},
    )
    r = client.get(
        f"/api/v1/plugins/ddw_member_vip/accounts/{aid}/transactions"
    )
    body = r.json()
    times = [t["created_at"] for t in body["transactions"]]
    assert times == sorted(times, reverse=True)


# === T9-6: stats ===
def test_T9_6_stats(client):
    aid = client.post(
        "/api/v1/plugins/ddw_member_vip/accounts",
        json={"patient_id": "pt_006"},
    ).json()["id"]
    client.post(
        f"/api/v1/plugins/ddw_member_vip/accounts/{aid}/recharge",
        json={"amount": 2000.0},
    )
    r = client.get("/api/v1/plugins/ddw_member_vip/stats")
    body = r.json()
    assert body["total_accounts"] >= 1
    assert body["total_recharged"] >= 2000.0
    assert "gold" in body["level_distribution"]


# === T9-7: 同 patient_id 不能创建两个 account ===
def test_T9_7_duplicate_patient_returns_409(client):
    client.post(
        "/api/v1/plugins/ddw_member_vip/accounts",
        json={"patient_id": "pt_dup"},
    )
    r = client.post(
        "/api/v1/plugins/ddw_member_vip/accounts",
        json={"patient_id": "pt_dup"},
    )
    assert r.status_code == 409


# === 附加 ===
def test_extra_health(client):
    assert client.get("/api/v1/plugins/ddw_member_vip/health").json()["status"] == "ok"


def test_extra_recharge_negative_400(client):
    aid = client.post(
        "/api/v1/plugins/ddw_member_vip/accounts",
        json={"patient_id": "pt_neg"},
    ).json()["id"]
    r = client.post(
        f"/api/v1/plugins/ddw_member_vip/accounts/{aid}/recharge",
        json={"amount": -100.0},
    )
    assert r.status_code == 400


def test_extra_diamond_level(client):
    aid = client.post(
        "/api/v1/plugins/ddw_member_vip/accounts",
        json={"patient_id": "pt_dia"},
    ).json()["id"]
    r = client.post(
        f"/api/v1/plugins/ddw_member_vip/accounts/{aid}/recharge",
        json={"amount": 5000.0},
    )
    body = r.json()
    assert body["level"] == "diamond"
    assert body["discount_rate"] == 0.85


def test_extra_recharge_nonexistent_account(client):
    r = client.post(
        "/api/v1/plugins/ddw_member_vip/accounts/mem_xxx/recharge",
        json={"amount": 100.0},
    )
    assert r.status_code == 400
