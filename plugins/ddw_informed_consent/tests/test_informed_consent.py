"""ddw_informed_consent 测试套件.

对齐 TASK_SPEC §T14:
  T14-1: 创建拔牙知情同意, status=pending
  T14-2: 签名后 status → signed, signed_at 非空
  T14-3: 7 个预置模板全部可列出
  T14-4: 关联 record_id 查询
  T14-5: 撤销签名 status → revoked
"""
from __future__ import annotations

import conftest  # noqa: F401  # pylint: disable=unused-import
import pytest
from plugins.ddw_informed_consent import router as plugin_router
from plugins.ddw_informed_consent.store import ConsentStore
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def app_instance(tmp_path):
    db = tmp_path / "consent.db"
    store = ConsentStore(db_path=db)
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
        "record_id": "emr_001",
        "consent_type": "treatment",
        "template_content": "拔牙知情同意书正文...",
    }
    base.update(over)
    return base


# === T14-1: 创建知情同意, status=pending ===
def test_T14_1_create_consent_pending(client):
    r = client.post(
        "/api/v1/plugins/ddw_informed_consent/records", json=_payload()
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending"


# === T14-2: 签名后 signed ===
def test_T14_2_sign_consent(client):
    cid = client.post(
        "/api/v1/plugins/ddw_informed_consent/records", json=_payload()
    ).json()["id"]
    resp = client.post(
        f"/api/v1/plugins/ddw_informed_consent/records/{cid}/sign",
        json={"patient_signature": "base64_png_data_here", "witness": "李护士"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "signed"
    assert body["signed_at"]
    assert body["witness"] == "李护士"


# === T14-3: 7 个预置模板 ===
def test_T14_3_seven_templates(client):
    resp = client.get("/api/v1/plugins/ddw_informed_consent/templates")
    body = resp.json()
    assert body["total"] == 7
    names = {t["name"] for t in body["templates"]}
    assert "拔牙知情同意书" in names
    assert "根管治疗知情同意书" in names
    assert "种植手术知情同意书" in names
    assert "正畸治疗知情同意书" in names
    assert "美容修复知情同意书" in names
    assert "麻醉知情同意书" in names
    assert "费用知情同意书" in names


# === T14-4: 关联 record_id 查询 ===
def test_T14_4_list_by_patient(client):
    client.post(
        "/api/v1/plugins/ddw_informed_consent/records",
        json=_payload(patient_id="pt_A", record_id="emr_A"),
    )
    client.post(
        "/api/v1/plugins/ddw_informed_consent/records",
        json=_payload(patient_id="pt_B", record_id="emr_B"),
    )
    resp = client.get(
        "/api/v1/plugins/ddw_informed_consent/records",
        params={"patient_id": "pt_A"},
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["records"][0]["record_id"] == "emr_A"


# === T14-5: 撤销签名 ===
def test_T14_5_revoke_signature(client):
    cid = client.post(
        "/api/v1/plugins/ddw_informed_consent/records", json=_payload()
    ).json()["id"]
    client.post(
        f"/api/v1/plugins/ddw_informed_consent/records/{cid}/sign",
        json={"patient_signature": "sig"},
    )
    resp = client.post(
        f"/api/v1/plugins/ddw_informed_consent/records/{cid}/revoke"
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"


# === 附加 ===
def test_extra_health(client):
    assert client.get(
        "/api/v1/plugins/ddw_informed_consent/health"
    ).json()["status"] == "ok"


def test_extra_invalid_type_400(client):
    r = client.post(
        "/api/v1/plugins/ddw_informed_consent/records",
        json=_payload(consent_type="invalid_xxx"),
    )
    assert r.status_code == 400


def test_extra_sign_404(client):
    resp = client.post(
        "/api/v1/plugins/ddw_informed_consent/records/ic_xxx/sign",
        json={"patient_signature": "x"},
    )
    assert resp.status_code == 404


def test_extra_sign_twice_400(client):
    cid = client.post(
        "/api/v1/plugins/ddw_informed_consent/records", json=_payload()
    ).json()["id"]
    client.post(
        f"/api/v1/plugins/ddw_informed_consent/records/{cid}/sign",
        json={"patient_signature": "x"},
    )
    r = client.post(
        f"/api/v1/plugins/ddw_informed_consent/records/{cid}/sign",
        json={"patient_signature": "y"},
    )
    assert r.status_code == 400


def test_extra_revoke_already_revoked_400(client):
    cid = client.post(
        "/api/v1/plugins/ddw_informed_consent/records", json=_payload()
    ).json()["id"]
    client.post(
        f"/api/v1/plugins/ddw_informed_consent/records/{cid}/revoke"
    )
    r = client.post(
        f"/api/v1/plugins/ddw_informed_consent/records/{cid}/revoke"
    )
    assert r.status_code == 400
