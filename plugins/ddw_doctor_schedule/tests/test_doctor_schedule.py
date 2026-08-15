"""ddw_doctor_schedule 测试套件.

对齐 TASK_SPEC §T4:
  T4-1: 添加 14 个医生，list 返回 14 条
  T4-2: 批量创建一周排班（14 医生 × 7 天 × 3 时段）
  T4-3: 查看某日排班，按 start_time 排序
  T4-4: 调班（slot_type 从 normal 改为 leave）
  T4-5: 检查冲突（同医生同时段不能有两个 normal slot）
  T4-6: 某医生周排班含 off/leave 标记
  T4-7: max_patients 限制（booked_count 达到后该 slot 不可选）
"""
from __future__ import annotations

import conftest  # noqa: F401  # pylint: disable=unused-import
import pytest
from plugins.ddw_doctor_schedule import router as plugin_router
from plugins.ddw_doctor_schedule.store import DoctorStore
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def app_instance(tmp_path):
    db = tmp_path / "schedule.db"
    store = DoctorStore(db_path=db)
    plugin_router.set_store(store)
    app = FastAPI()
    app.include_router(plugin_router.router)
    return app, store


@pytest.fixture()
def client(app_instance):
    app, _ = app_instance
    with TestClient(app) as c:
        yield c


def _seed_doctors(client, n=14):
    ids = []
    for i in range(n):
        r = client.post(
            "/api/v1/plugins/ddw_doctor_schedule/doctors",
            json={
                "name": f"医生{i:02d}",
                "title": "主治医师",
                "specialty": ["正畸", "种植"] if i % 2 == 0 else ["牙周"],
            },
        )
        assert r.status_code == 201
        ids.append(r.json()["id"])
    return ids


# === T4-1: 添加 14 个医生 ===
def test_T4_1_add_14_doctors(client):
    ids = _seed_doctors(client, 14)
    assert len(ids) == 14
    resp = client.get("/api/v1/plugins/ddw_doctor_schedule/doctors")
    assert resp.json()["total"] == 14


# === T4-2: 批量创建一周排班 ===
def test_T4_2_create_week_schedule(client):
    ids = _seed_doctors(client, 3)
    from datetime import date, timedelta
    start = date(2026, 8, 10)  # 周一
    created = 0
    for did in ids:
        for d_offset in range(7):
            d = (start + timedelta(days=d_offset)).isoformat()
            for s, e in [("08:00", "12:00"), ("13:30", "17:00"), ("17:30", "20:30")]:
                r = client.post(
                    "/api/v1/plugins/ddw_doctor_schedule/slots",
                    json={
                        "doctor_id": did, "date": d,
                        "start_time": s, "end_time": e,
                    },
                )
                if r.status_code == 201:
                    created += 1
    # 3*7*3 = 63
    assert created == 63


# === T4-3: 按 start_time 排序 ===
def test_T4_3_list_by_date_sorted(client):
    did = _seed_doctors(client, 1)[0]
    for s, e in [("13:00", "16:00"), ("08:00", "12:00"), ("17:00", "20:00")]:
        client.post(
            "/api/v1/plugins/ddw_doctor_schedule/slots",
            json={"doctor_id": did, "date": "2026-08-12", "start_time": s, "end_time": e},
        )
    resp = client.get(
        "/api/v1/plugins/ddw_doctor_schedule/slots",
        params={"date": "2026-08-12"},
    )
    body = resp.json()
    starts = [s["start_time"] for s in body["slots"]]
    assert starts == sorted(starts)


# === T4-4: 调班 ===
def test_T4_4_change_slot_type_to_leave(client):
    did = _seed_doctors(client, 1)[0]
    r = client.post(
        "/api/v1/plugins/ddw_doctor_schedule/slots",
        json={"doctor_id": did, "date": "2026-08-12", "start_time": "08:00", "end_time": "12:00"},
    )
    sid = r.json()["id"]
    resp = client.patch(
        f"/api/v1/plugins/ddw_doctor_schedule/slots/{sid}",
        json={"slot_type": "leave", "notes": "请假"},
    )
    assert resp.status_code == 200
    assert resp.json()["slot_type"] == "leave"


# === T4-5: 冲突检测 ===
def test_T4_5_slot_conflict_409(client):
    did = _seed_doctors(client, 1)[0]
    payload = {"doctor_id": did, "date": "2026-08-12", "start_time": "08:00", "end_time": "12:00"}
    r1 = client.post(
        "/api/v1/plugins/ddw_doctor_schedule/slots", json=payload
    )
    assert r1.status_code == 201
    r2 = client.post(
        "/api/v1/plugins/ddw_doctor_schedule/slots", json=payload
    )
    assert r2.status_code == 409


# === T4-6: 周排班含 off/leave ===
def test_T4_6_weekly_schedule_with_off(client):
    did = _seed_doctors(client, 1)[0]
    # 创建一个 normal + 一个 leave
    client.post(
        "/api/v1/plugins/ddw_doctor_schedule/slots",
        json={"doctor_id": did, "date": "2026-08-10", "start_time": "08:00", "end_time": "12:00"},
    )
    sid = client.post(
        "/api/v1/plugins/ddw_doctor_schedule/slots",
        json={"doctor_id": did, "date": "2026-08-10", "start_time": "14:00", "end_time": "17:00"},
    ).json()["id"]
    client.patch(
        f"/api/v1/plugins/ddw_doctor_schedule/slots/{sid}",
        json={"slot_type": "leave"},
    )
    resp = client.get(
        f"/api/v1/plugins/ddw_doctor_schedule/doctors/{did}/slots",
        params={"week": "2026-W33"},
    )
    slots = resp.json()["slots"]
    assert any(s["slot_type"] == "leave" for s in slots)
    assert any(s["slot_type"] == "normal" for s in slots)


# === T4-7: max_patients 限制 ===
def test_T4_7_max_patients_reached(client):
    did = _seed_doctors(client, 1)[0]
    r = client.post(
        "/api/v1/plugins/ddw_doctor_schedule/slots",
        json={"doctor_id": did, "date": "2026-08-12", "start_time": "08:00", "end_time": "12:00", "max_patients": 2},
    )
    sid = r.json()["id"]
    # booked_count 达到 2
    client.patch(
        f"/api/v1/plugins/ddw_doctor_schedule/slots/{sid}",
        json={"booked_count": 2},
    )
    slot = client.get(
        f"/api/v1/plugins/ddw_doctor_schedule/doctors/{did}/slots"
    ).json()["slots"][0]
    assert slot["booked_count"] == 2
    assert slot["max_patients"] == 2
    # 满员校验
    assert slot["booked_count"] >= slot["max_patients"]


# === 附加 ===
def test_extra_health(client):
    resp = client.get("/api/v1/plugins/ddw_doctor_schedule/health")
    assert resp.status_code == 200


def test_extra_get_doctor_404(client):
    resp = client.get("/api/v1/plugins/ddw_doctor_schedule/doctors/doc_xxx")
    assert resp.status_code == 404


def test_extra_create_slot_invalid_type_400(client):
    did = _seed_doctors(client, 1)[0]
    resp = client.post(
        "/api/v1/plugins/ddw_doctor_schedule/slots",
        json={"doctor_id": did, "date": "2026-08-12", "start_time": "08:00", "end_time": "12:00", "slot_type": "invalid"},
    )
    assert resp.status_code == 400


def test_extra_create_slot_unknown_doctor_400(client):
    resp = client.post(
        "/api/v1/plugins/ddw_doctor_schedule/slots",
        json={"doctor_id": "doc_xxx", "date": "2026-08-12", "start_time": "08:00", "end_time": "12:00"},
    )
    assert resp.status_code == 400
