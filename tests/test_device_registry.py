"""P0-3（multidevice）：设备身份/在线状态测试。

验收：设备首次注册 → 刷新/重启后身份不变（同一 device_id）；断开后
/status 中 60s 内消失；重连后恢复在线；状态 API 无 Token → 401。
"""

from __future__ import annotations

import os
import time

os.environ.setdefault("DDW_ACCESS_TOKEN", "test-device-registry-token")

import pytest  # noqa: E402

from core.api import status as status_api  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch, tmp_path):
    """设备表独立库 + 清内存活跃表。"""
    monkeypatch.setattr(status_api, "_db_path", lambda: tmp_path / "devices.db")
    with status_api._active_lock:
        status_api._active.clear()
    with status_api._stats_lock:
        status_api._request_count = 0
        status_api._ws_count = 0
    yield
    with status_api._active_lock:
        status_api._active.clear()


def _reg(device_id: str, name: str = "测试设备") -> dict:
    return status_api.register_device(device_id, name, ip="192.168.1.50")


def test_device_register_idempotent_and_identity_stable(tmp_path):
    """首次注册 + 重复注册 → 同一 device_id，身份不变（registered 只在首资）。"""
    r1 = _reg("device-abc-0001", "手机")
    assert r1["ok"] and r1["registered"] is True
    r2 = _reg("device-abc-0001", "手机改名片")
    assert r2["ok"] and r2["registered"] is False  # 幂等
    r3 = _reg("device-abc-0001")
    assert r3["ok"] and r3["registered"] is False
    snap = status_api.status_snapshot()
    devs = [d for d in snap["devices"] if d["device_id"] == "device-abc-0001"]
    assert len(devs) == 1  # 无重复行
    assert devs[0]["device_name"] == "测试设备"  # 最后一次 name 更新


def test_device_reconnect_same_identity(tmp_path):
    """模拟"重启"：再次注册同一 device_id → 仍同一身份（覆盖而非新增）。"""
    _reg("device-abc-0002", "笔记本")
    # 模拟重启：内存活跃表清空（进程内状态丢失），设备表保留
    with status_api._active_lock:
        status_api._active.clear()
    r = _reg("device-abc-0002", "笔记本")
    assert r["ok"] and r["registered"] is False  # 身份延续
    snap = status_api.status_snapshot()
    assert len([d for d in snap["devices"] if d["device_id"] == "device-abc-0002"]) == 1


def test_device_offline_after_window(tmp_path, monkeypatch):
    """断开后超过 60s 窗口 → 状态中消失（online=False）。"""
    _reg("device-abc-0003", "平板")
    # 在线
    snap = status_api.status_snapshot()
    d = [x for x in snap["devices"] if x["device_id"] == "device-abc-0003"][0]
    assert d["online"] is True
    # 时间推进 61s（模拟无心跳）
    future = time.time() + 61
    monkeypatch.setattr(status_api.time, "time", lambda: future)
    snap2 = status_api.status_snapshot()
    d2 = [x for x in snap2["devices"] if x["device_id"] == "device-abc-0003"][0]
    assert d2["online"] is False
    assert snap2["online_devices"] == 0


def test_touch_keeps_online(tmp_path, monkeypatch):
    """心跳触碰 → 保持在线。"""
    _reg("device-abc-0004", "手机")
    now = time.time()
    for i in range(3):
        future = now + 30 * (i + 1)
        monkeypatch.setattr(status_api.time, "time", lambda: future)
        status_api.touch_device("device-abc-0004")
    snap = status_api.status_snapshot()
    d = [x for x in snap["devices"] if x["device_id"] == "device-abc-0004"][0]
    assert d["online"] is True


async def test_status_api_requires_auth(client):
    """状态 API 无 Token → 401。"""
    resp = await client.get("/api/v1/status")
    assert resp.status_code == 401


async def test_status_api_returns_fields(client, monkeypatch, tmp_path):
    """状态 API 字段齐全（在线设备/WS/请求/DB 大小/版本）。"""
    monkeypatch.setattr(status_api, "_db_path", lambda: tmp_path / "devices.db")
    with status_api._active_lock:
        status_api._active.clear()
    headers = {"X-DDW-Token": os.environ["DDW_ACCESS_TOKEN"]}
    # 注册一台设备
    resp = await client.post("/api/v1/device/register", headers=headers,
                             json={"device_id": "device-abc-0005",
                                   "device_name": "双开窗口A"})
    assert resp.status_code == 200 and resp.json()["data"]["ok"]
    resp2 = await client.post("/api/v1/device/register", headers=headers,
                              json={"device_id": "device-abc-0006",
                                    "device_name": "双开窗口B"})
    assert resp2.status_code == 200
    snap_resp = await client.get("/api/v1/status", headers=headers)
    assert snap_resp.status_code == 200
    data = snap_resp.json()["data"]
    for field in ("online_devices", "devices", "active_ws", "requests",
                  "db_size_bytes", "version"):
        assert field in data, field
    assert data["online_devices"] == 2  # 双设备在线计数
    names = {d["device_name"] for d in data["devices"]}
    assert {"双开窗口A", "双开窗口B"} <= names
