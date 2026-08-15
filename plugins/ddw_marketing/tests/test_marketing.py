"""ddw_marketing 测试套件.

对齐 TASK_SPEC §T11:
  T11-1: 创建活动, target_tags=["老患者"], 预估接收人数正确
  T11-2: 发送后 sent_count 增加
  T11-3: stats 返回 sent/click/conversion_rate
"""
from __future__ import annotations

import conftest  # noqa: F401  # pylint: disable=unused-import
import pytest
from plugins.ddw_marketing import router as plugin_router
from plugins.ddw_marketing.store import CampaignStore
from plugins.ddw_patient_crm import router as crm_router
from plugins.ddw_patient_crm.store import PatientStore
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def setup(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    mkt = CampaignStore(db_path=data / "marketing.db")
    crm = PatientStore(db_path=data / "patient_crm.db")
    plugin_router.set_store(mkt)
    crm_router.set_store(crm)
    app = FastAPI()
    app.include_router(plugin_router.router)
    app.include_router(crm_router.router)
    return app, mkt, crm, data


@pytest.fixture()
def client(setup):
    app, _, _, _ = setup
    with TestClient(app) as c:
        yield c


# === T11-1: target_tags 预估接收人数 ===
def test_T11_1_estimate_recipients(setup):
    _app, _mkt, crm, _ = setup
    # 创建 2 个老患者 + 1 个新患者
    crm.create({"name": "老A", "phone": "13900000011", "tags": ["老患者"]})
    crm.create({"name": "老B", "phone": "13900000012", "tags": ["老患者", "VIP"]})
    crm.create({"name": "新C", "phone": "13900000013", "tags": []})
    # 创建营销活动
    from ddw_marketing.targeter import estimate_recipients
    n = estimate_recipients(_mkt.db_path, target_tags=["老患者"], target_levels=[])
    assert n == 2


# === T11-2: 发送后 sent_count 增加 ===
def test_T11_2_send_updates_count(client, setup):
    _app, _mkt, crm, _ = setup
    crm.create({"name": "A", "phone": "13900000021", "tags": ["老患者"]})
    crm.create({"name": "B", "phone": "13900000022", "tags": ["老患者"]})
    cid = client.post(
        "/api/v1/plugins/ddw_marketing/campaigns",
        json={"name": "夏日优惠", "content": "全场 8 折", "target_tags": ["老患者"]},
    ).json()["id"]
    resp = client.post(
        f"/api/v1/plugins/ddw_marketing/campaigns/{cid}/send"
    )
    body = resp.json()
    assert body["status"] == "sent"
    assert body["sent_count"] == 2


# === T11-3: stats ===
def test_T11_3_stats_response(client, setup):
    _app, _mkt, crm, _ = setup
    crm.create({"name": "A", "phone": "13900000031", "tags": ["老患者"]})
    cid = client.post(
        "/api/v1/plugins/ddw_marketing/campaigns",
        json={"name": "C", "content": "x", "target_tags": ["老患者"]},
    ).json()["id"]
    client.post(f"/api/v1/plugins/ddw_marketing/campaigns/{cid}/send")
    resp = client.get(
        f"/api/v1/plugins/ddw_marketing/campaigns/{cid}/stats"
    )
    body = resp.json()
    assert body["sent"] == 1
    assert body["click"] == 0
    assert body["conversion_rate"] == 0.0


# === 附加 ===
def test_extra_health(client):
    assert client.get("/api/v1/plugins/ddw_marketing/health").json()["status"] == "ok"


def test_extra_send_twice_400(client):
    cid = client.post(
        "/api/v1/plugins/ddw_marketing/campaigns",
        json={"name": "C", "content": "x"},
    ).json()["id"]
    client.post(f"/api/v1/plugins/ddw_marketing/campaigns/{cid}/send")
    resp = client.post(f"/api/v1/plugins/ddw_marketing/campaigns/{cid}/send")
    assert resp.status_code == 400


def test_extra_send_404(client):
    resp = client.post(
        "/api/v1/plugins/ddw_marketing/campaigns/camp_xxx/send"
    )
    assert resp.status_code == 404


def test_extra_create_empty_name_400(client):
    resp = client.post(
        "/api/v1/plugins/ddw_marketing/campaigns",
        json={"name": "", "content": "x"},
    )
    assert resp.status_code == 400
