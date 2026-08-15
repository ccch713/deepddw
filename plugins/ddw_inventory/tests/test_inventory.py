"""ddw_inventory 测试套件.

对齐 TASK_SPEC §T7:
  T7-1: 添加耗材, 入库 +100, quantity = 100
  T7-2: 出库 -10, quantity = 90
  T7-3: 出库超出库存返回 400
  T7-4: alerts 含 low_stock
  T7-5: alerts 含 expiring_soon (30 天内)
  T7-6: 操作日志记录完整
"""
from __future__ import annotations

from datetime import datetime, timedelta

import conftest  # noqa: F401  # pylint: disable=unused-import
import pytest
from plugins.ddw_inventory import router as plugin_router
from plugins.ddw_inventory.store import InventoryStore
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def app_instance(tmp_path):
    db = tmp_path / "inv.db"
    store = InventoryStore(db_path=db)
    plugin_router.set_store(store)
    app = FastAPI()
    app.include_router(plugin_router.router)
    return app, store


@pytest.fixture()
def client(app_instance):
    app, _ = app_instance
    with TestClient(app) as c:
        yield c


def _item_payload(**over):
    base = {
        "name": "麻药",
        "category": "consumable",
        "quantity": 0,
        "unit": "支",
        "min_quantity": 10,
    }
    base.update(over)
    return base


# === T7-1: 入库 +100 ===
def test_T7_1_stock_in_quantity_100(client):
    r = client.post("/api/v1/plugins/ddw_inventory/items", json=_item_payload())
    iid = r.json()["id"]
    resp = client.post(
        f"/api/v1/plugins/ddw_inventory/items/{iid}/in",
        json={"quantity_change": 100, "reason": "采购", "operator": "张医生"},
    )
    assert resp.json()["quantity"] == 100


# === T7-2: 出库 -10 ===
def test_T7_2_stock_out_quantity_90(client):
    iid = client.post(
        "/api/v1/plugins/ddw_inventory/items", json=_item_payload()
    ).json()["id"]
    client.post(
        f"/api/v1/plugins/ddw_inventory/items/{iid}/in",
        json={"quantity_change": 100},
    )
    resp = client.post(
        f"/api/v1/plugins/ddw_inventory/items/{iid}/out",
        json={"quantity_change": 10, "reason": "治疗使用"},
    )
    assert resp.json()["quantity"] == 90


# === T7-3: 出库超出库存 400 ===
def test_T7_3_overdraw_returns_400(client):
    iid = client.post(
        "/api/v1/plugins/ddw_inventory/items", json=_item_payload()
    ).json()["id"]
    client.post(
        f"/api/v1/plugins/ddw_inventory/items/{iid}/in",
        json={"quantity_change": 5},
    )
    resp = client.post(
        f"/api/v1/plugins/ddw_inventory/items/{iid}/out",
        json={"quantity_change": 100},
    )
    assert resp.status_code == 400
    assert "不足" in resp.json()["detail"]


# === T7-4: alerts low_stock ===
def test_T7_4_alerts_low_stock(client):
    # 创建一个 min=10 但 quantity=0
    client.post(
        "/api/v1/plugins/ddw_inventory/items",
        json=_item_payload(name="缺货耗材", min_quantity=10, quantity=0),
    )
    resp = client.get("/api/v1/plugins/ddw_inventory/alerts")
    body = resp.json()
    assert any(it["name"] == "缺货耗材" for it in body["low_stock"])


# === T7-5: alerts expiring_soon ===
def test_T7_5_alerts_expiring_soon(client):
    soon = (datetime.now() + timedelta(days=15)).strftime("%Y-%m-%d")
    client.post(
        "/api/v1/plugins/ddw_inventory/items",
        json=_item_payload(name="快过期", expiry_date=soon),
    )
    resp = client.get("/api/v1/plugins/ddw_inventory/alerts")
    body = resp.json()
    assert any(it["name"] == "快过期" for it in body["expiring_soon"])


# === T7-6: 操作日志完整 ===
def test_T7_6_log_full_info(client):
    iid = client.post(
        "/api/v1/plugins/ddw_inventory/items", json=_item_payload()
    ).json()["id"]
    client.post(
        f"/api/v1/plugins/ddw_inventory/items/{iid}/in",
        json={"quantity_change": 50, "reason": "采购", "operator": "张医生"},
    )
    client.post(
        f"/api/v1/plugins/ddw_inventory/items/{iid}/out",
        json={"quantity_change": 5, "reason": "领用", "operator": "李医生"},
    )
    resp = client.get(
        "/api/v1/plugins/ddw_inventory/logs",
        params={"item_id": iid},
    )
    logs = resp.json()["logs"]
    assert len(logs) == 2
    actions = {l["action"] for l in logs}
    assert "in" in actions and "out" in actions
    assert all(l["operator"] and l["reason"] and l["created_at"] for l in logs)


# === 附加 ===
def test_extra_health(client):
    assert client.get("/api/v1/plugins/ddw_inventory/health").json()["status"] == "ok"


def test_extra_create_item_invalid_category(client):
    resp = client.post(
        "/api/v1/plugins/ddw_inventory/items",
        json=_item_payload(category="invalid_xxx"),
    )
    assert resp.status_code == 400


def test_extra_get_404(client):
    assert client.get(
        "/api/v1/plugins/ddw_inventory/items/inv_xxx"
    ).status_code == 404


def test_extra_adjust(client):
    iid = client.post(
        "/api/v1/plugins/ddw_inventory/items", json=_item_payload(quantity=10)
    ).json()["id"]
    resp = client.post(
        f"/api/v1/plugins/ddw_inventory/items/{iid}/adjust",
        params={"new_quantity": 50, "reason": "盘点"},
    )
    assert resp.status_code == 200
    assert resp.json()["quantity"] == 50


def test_extra_in_negative_qty_400(client):
    iid = client.post(
        "/api/v1/plugins/ddw_inventory/items", json=_item_payload()
    ).json()["id"]
    resp = client.post(
        f"/api/v1/plugins/ddw_inventory/items/{iid}/in",
        json={"quantity_change": -10},
    )
    assert resp.status_code == 400
