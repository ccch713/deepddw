"""ddw_dental_imaging 测试套件.

对齐 TASK_SPEC §T12:
  T12-1: 上传口腔照片, 文件存入对应目录
  T12-2: 按 patient_id + image_type 筛选
  T12-3: 时间轴返回按 taken_at 排序
  T12-4: 删除影像, 文件物理删除
  T12-5: 上传非图片文件返回 400
"""
from __future__ import annotations

import conftest  # noqa: F401  # pylint: disable=unused-import
import pytest
from plugins.ddw_dental_imaging import router as plugin_router
from plugins.ddw_dental_imaging.store import ImageStore
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def app_instance(tmp_path):
    db = tmp_path / "img.db"
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    store = ImageStore(db_path=db, root_dir=img_dir)
    plugin_router.set_store(store)
    app = FastAPI()
    app.include_router(plugin_router.router)
    return app, store, img_dir


@pytest.fixture()
def client(app_instance):
    app, _, _ = app_instance
    with TestClient(app) as c:
        yield c


def _png_bytes() -> bytes:
    """最小合法 PNG (1x1 透明)."""
    import base64
    return base64.b64decode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNgAAIAAAUAAen63NgAAAAASUVORK5CYII="
    )


# === T12-1: 上传影像 ===
def test_T12_1_upload_image(client, app_instance):
    _app, _store, img_dir = app_instance
    resp = client.post(
        "/api/v1/plugins/ddw_dental_imaging/images",
        files={"file": ("test.png", _png_bytes(), "image/png")},
        data={"patient_id": "pt_001", "image_type": "intraoral"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["file_path"]
    # 文件落盘
    files = list(img_dir.rglob("*.png"))
    assert len(files) == 1


# === T12-2: 按 patient + type 筛选 ===
def test_T12_2_filter_by_patient_type(client, app_instance):
    _app, _store, _ = app_instance
    for tt in ("intraoral", "xray", "intraoral"):
        client.post(
            "/api/v1/plugins/ddw_dental_imaging/images",
            files={"file": (f"a_{tt}.png", _png_bytes(), "image/png")},
            data={"patient_id": "pt_x", "image_type": tt},
        )
    resp = client.get(
        "/api/v1/plugins/ddw_dental_imaging/images",
        params={"patient_id": "pt_x", "image_type": "intraoral"},
    )
    assert resp.json()["total"] == 2


# === T12-3: 时间轴排序 ===
def test_T12_3_timeline_ordering(client, app_instance):
    _app, _store, _ = app_instance
    for t in ("2026-08-01", "2026-08-05", "2026-08-03"):
        client.post(
            "/api/v1/plugins/ddw_dental_imaging/images",
            files={"file": (f"{t}.png", _png_bytes(), "image/png")},
            data={
                "patient_id": "pt_t",
                "image_type": "xray",
                "taken_at": f"{t}T10:00:00Z",
            },
        )
    resp = client.get(
        "/api/v1/plugins/ddw_dental_imaging/timeline",
        params={"patient_id": "pt_t"},
    )
    body = resp.json()
    times = [i["taken_at"] for i in body["timeline"]]
    assert times == sorted(times)


# === T12-4: 删除影像, 物理删文件 ===
def test_T12_4_delete_physically_removes_file(client, app_instance):
    _app, _store, _img_dir = app_instance
    r = client.post(
        "/api/v1/plugins/ddw_dental_imaging/images",
        files={"file": ("del.png", _png_bytes(), "image/png")},
        data={"patient_id": "pt_d", "image_type": "photo"},
    )
    iid = r.json()["id"]
    file_path = r.json()["file_path"]
    from pathlib import Path
    assert Path(file_path).exists()
    resp = client.delete(
        f"/api/v1/plugins/ddw_dental_imaging/images/{iid}"
    )
    assert resp.status_code == 204
    assert not Path(file_path).exists()


# === T12-5: 非图片文件 400 ===
def test_T12_5_non_image_400(client):
    resp = client.post(
        "/api/v1/plugins/ddw_dental_imaging/images",
        files={"file": ("a.txt", b"hello", "text/plain")},
        data={"patient_id": "pt_x", "image_type": "intraoral"},
    )
    assert resp.status_code == 400


# === 附加 ===
def test_extra_health(client):
    assert client.get("/api/v1/plugins/ddw_dental_imaging/health").json()["status"] == "ok"


def test_extra_get_404(client):
    assert client.get(
        "/api/v1/plugins/ddw_dental_imaging/images/img_xxx"
    ).status_code == 404


def test_extra_invalid_type_400(client):
    resp = client.post(
        "/api/v1/plugins/ddw_dental_imaging/images",
        files={"file": ("a.png", _png_bytes(), "image/png")},
        data={"patient_id": "pt_x", "image_type": "invalid_xxx"},
    )
    assert resp.status_code == 400
