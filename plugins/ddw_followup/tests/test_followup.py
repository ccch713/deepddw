"""ddw_followup 测试套件.

对齐 TASK_SPEC §T8:
  T8-1: 创建拔牙术后回访, due_date = 就诊 + 1
  T8-2: 查询 pending 任务
  T8-3: 更新状态 sent → responded
  T8-4: stats 按 followup_type 分组
  T8-5: 4 个预置模板
  T8-6: 同 patient+type 不重复
"""
from __future__ import annotations

from datetime import datetime, timedelta

import conftest  # noqa: F401  # pylint: disable=unused-import
import pytest
from plugins.ddw_followup import router as plugin_router
from plugins.ddw_followup.store import FollowupStore
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def app_instance(tmp_path):
    db = tmp_path / "followup.db"
    store = FollowupStore(db_path=db)
    plugin_router.set_store(store)
    app = FastAPI()
    app.include_router(plugin_router.router)
    return app, store


@pytest.fixture()
def client(app_instance):
    app, _ = app_instance
    with TestClient(app) as c:
        yield c


def _task(**over):
    base = {
        "patient_id": "pt_001",
        "doctor_id": "doc_001",
        "followup_type": "postop_recall",
        "due_date": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
        "message_template": "术后关怀内容",
    }
    base.update(over)
    return base


# === T8-1: 拔牙术后回访 ===
def test_T8_1_create_postop_recall_task(client):
    r = client.post("/api/v1/plugins/ddw_followup/tasks", json=_task())
    assert r.status_code == 201
    body = r.json()
    assert body["followup_type"] == "postop_recall"
    assert body["status"] == "pending"
    assert body["due_date"]


# === T8-2: pending 任务 ===
def test_T8_2_list_pending_tasks(client):
    client.post("/api/v1/plugins/ddw_followup/tasks", json=_task())
    client.post(
        "/api/v1/plugins/ddw_followup/tasks",
        json=_task(patient_id="pt_002"),
    )
    resp = client.get(
        "/api/v1/plugins/ddw_followup/tasks",
        params={"status": "pending"},
    )
    assert resp.json()["total"] >= 2


# === T8-3: sent → responded ===
def test_T8_3_status_sent_then_responded(client):
    tid = client.post(
        "/api/v1/plugins/ddw_followup/tasks", json=_task()
    ).json()["id"]
    r1 = client.patch(
        f"/api/v1/plugins/ddw_followup/tasks/{tid}",
        json={"status": "sent"},
    )
    assert r1.json()["status"] == "sent"
    assert r1.json()["sent_at"]
    r2 = client.patch(
        f"/api/v1/plugins/ddw_followup/tasks/{tid}",
        json={"status": "responded"},
    )
    assert r2.json()["status"] == "responded"


# === T8-4: stats 按 type 分组 ===
def test_T8_4_stats_by_type(client):
    today = datetime.now().strftime("%Y-%m")
    client.post(
        "/api/v1/plugins/ddw_followup/tasks",
        json=_task(followup_type="postop_recall"),
    )
    client.post(
        "/api/v1/plugins/ddw_followup/tasks",
        json=_task(patient_id="pt_002", followup_type="satisfaction"),
    )
    resp = client.get(
        "/api/v1/plugins/ddw_followup/stats",
        params={"period": today},
    )
    body = resp.json()
    assert "postop_recall" in body["by_type"]
    assert "satisfaction" in body["by_type"]


# === T8-5: 4 个预置模板 ===
def test_T8_5_default_templates_seeded(client):
    resp = client.get("/api/v1/plugins/ddw_followup/templates")
    body = resp.json()
    assert body["total"] >= 4
    names = {t["name"] for t in body["templates"]}
    assert "拔牙术后关怀" in names
    assert "根管治疗复诊" in names
    assert "种植术后关怀" in names
    assert "满意度回访" in names


# === T8-6: 同 patient+type 不重复 ===
def test_T8_6_no_duplicate_pending(client):
    client.post(
        "/api/v1/plugins/ddw_followup/tasks", json=_task()
    )
    r2 = client.post(
        "/api/v1/plugins/ddw_followup/tasks", json=_task()
    )
    # 第二次返回的是已存在的
    assert r2.status_code == 201
    list_resp = client.get(
        "/api/v1/plugins/ddw_followup/tasks",
        params={"status": "pending"},
    )
    pending_for_pt1 = [
        t for t in list_resp.json()["tasks"]
        if t["patient_id"] == "pt_001" and t["followup_type"] == "postop_recall"
    ]
    assert len(pending_for_pt1) == 1


# === 附加 ===
def test_extra_health(client):
    assert client.get("/api/v1/plugins/ddw_followup/health").json()["status"] == "ok"


def test_extra_invalid_type_400(client):
    r = client.post(
        "/api/v1/plugins/ddw_followup/tasks",
        json=_task(followup_type="invalid_xxx"),
    )
    assert r.status_code == 400


def test_extra_update_invalid_status_400(client):
    tid = client.post(
        "/api/v1/plugins/ddw_followup/tasks", json=_task()
    ).json()["id"]
    r = client.patch(
        f"/api/v1/plugins/ddw_followup/tasks/{tid}",
        json={"status": "invalid_xxx"},
    )
    assert r.status_code == 400


def test_extra_create_custom_template(client):
    r = client.post(
        "/api/v1/plugins/ddw_followup/templates",
        json={
            "name": "正畸复诊",
            "followup_type": "custom",
            "delay_days": 30,
            "message_template": "记得按时复诊",
        },
    )
    assert r.status_code == 201
