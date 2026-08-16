"""P0-3 / P0-4（multidevice）：设备身份/在线/会话映射 + 状态面板 API。

- 设备注册表（SQLite 表 devices，同步连接与 knowledge.py 同源）：
  device_id（客户端 localStorage 持久化）/ device_name / ip / first_seen /
  last_seen；在线判定 = last_seen 距今 < 60s（心跳/请求/WS 连接刷新）。
- 内存活跃表（{device_id: last_seen}）供高频心跳，定期落库。
- 端点（全部 Token 门禁，向后兼容只增不改）：
  POST /api/v1/device/register  注册/改名（body: device_id, device_name?）
  POST /api/v1/device/heartbeat 心跳（body: device_id, device_name?）
  GET  /api/v1/status           状态面板（在线设备/活跃 WS/请求计数/DB 大小/版本）
- WS 代理接入：dsh_ws_proxy 打开时记录设备在线、关闭时标记离开。
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core.api_response import ok
from core.config import get_settings
from core.security.token_gate import require_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["multidevice", "status"])

# 在线判定窗口（秒）：超过即视为离线
ONLINE_WINDOW = 60
# 设备注册表清理阈值：超过 N 天未见的设备从表删除（可配置）
_DEVICE_PURGE_DAYS = 30

# 内存活跃表（进程内高频心跳，定期合并落库）
_active: Dict[str, float] = {}
_active_lock = threading.Lock()

# 请求计数（进程内计数器；状态面板展示）
_request_count = 0
_ws_count = 0
_stats_lock = threading.Lock()


class DeviceRegisterReq(BaseModel):
    device_id: str = Field(..., min_length=8, max_length=64)
    device_name: str = Field(default="", max_length=60)
    workspace: str = Field(default="shared", max_length=32)


class DeviceHeartbeatReq(BaseModel):
    device_id: str = Field(..., min_length=8, max_length=64)
    device_name: str = Field(default="", max_length=60)
    workspace: str = Field(default="shared", max_length=32)


def _db_path() -> Path:
    settings = get_settings()
    cfg = settings.databases.get("main", {})
    if cfg.get("engine") == "sqlite":
        return Path(cfg.get("path", "./data/ddw_main.db")).resolve()
    return Path("./data/ddw_main.db").resolve()


def _ensure_devices_table(conn) -> None:  # noqa: ANN001
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS devices (
            device_id   TEXT PRIMARY KEY,
            device_name TEXT NOT NULL DEFAULT '',
            ip          TEXT NOT NULL DEFAULT '',
            workspace   TEXT NOT NULL DEFAULT 'shared',
            first_seen  TEXT NOT NULL,
            last_seen   TEXT NOT NULL
        )
        """
    )
    conn.commit()
    # P1-1：workspace 列幂等迁移（旧表补列）
    try:
        conn.execute(
            "ALTER TABLE devices ADD COLUMN workspace TEXT NOT NULL DEFAULT 'shared'"
        )
        conn.commit()
    except Exception:  # noqa: BLE001  # 列已存在（幂等）
        pass


def _get_conn():
    """设备表专用连接（独立于 knowledge 的连接池，避免跨模块锁纠缠）。"""
    import sqlite3

    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error:  # noqa: BLE001
        pass
    _ensure_devices_table(conn)
    return conn


def _flush_active() -> None:
    """把内存活跃表合并落库（last_seen）。"""
    with _active_lock:
        if not _active:
            return
        snap = dict(_active)
    try:
        conn = _get_conn()
        try:
            for device_id, ts in snap.items():
                conn.execute(
                    "UPDATE devices SET last_seen=? WHERE device_id=?",
                    (_iso(ts), device_id),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        logger.debug("device flush degraded: %s", exc)


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _purge_stale() -> None:
    """清理超过 N 天未见的设备（注册表防增长）。"""
    try:
        conn = _get_conn()
        try:
            conn.execute(
                "DELETE FROM devices WHERE last_seen < datetime('now', ?)",
                (f"-{_DEVICE_PURGE_DAYS} days",),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        logger.debug("device purge degraded: %s", exc)


def register_device(
    device_id: str, device_name: str = "", ip: str = "", ts: Optional[float] = None,
    workspace: str = "shared",
) -> Dict[str, Any]:
    """注册/更新设备（幂等：device_id 不变，刷新 last_seen）。

    P1-1：设备携带 workspace（默认 shared，向后兼容）。
    """
    device_id = (device_id or "").strip()
    if len(device_id) < 8:
        return {"ok": False, "note": "invalid device_id (min 8 chars)"}
    w = (workspace or "").strip() or "shared"
    if not __import__("re").match(r"^[A-Za-z0-9_\-]{1,32}$", w):
        w = "shared"
    ts = ts or time.time()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT device_id FROM devices WHERE device_id=?", (device_id,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO devices "
                "(device_id, device_name, ip, workspace, first_seen, last_seen) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (device_id, (device_name or "")[:60], ip, w, _iso(ts), _iso(ts)),
            )
        else:
            conn.execute(
                "UPDATE devices SET device_name=?, ip=?, workspace=?, "
                "last_seen=? WHERE device_id=?",
                ((device_name or "")[:60], ip, w, _iso(ts), device_id),
            )
        conn.commit()
        with _active_lock:
            _active[device_id] = ts
        _purge_stale()
        return {"ok": True, "device_id": device_id, "registered": row is None}
    except Exception as exc:  # noqa: BLE001
        logger.warning("device register degraded: %s", exc)
        return {"ok": False, "degraded": True, "note": str(exc)}
    finally:
        conn.close()


def heartbeat_device(
    device_id: str, device_name: str = "", ip: str = "", ts: Optional[float] = None,
) -> Dict[str, Any]:
    """心跳：刷新内存活跃表 + 落库（幂等；未注册设备自动注册）。"""
    return register_device(device_id, device_name, ip, ts, workspace)


def touch_device(device_id: str) -> None:
    """轻量触碰（WS 连接/任意 API 请求时刷新在线，不落库高频）。"""
    if not device_id:
        return
    with _active_lock:
        _active[device_id] = time.time()


def leave_device(device_id: str) -> None:
    """设备离开（WS 关闭）：从内存活跃表移除（落库由 flush 兜底）。"""
    if not device_id:
        return
    with _active_lock:
        _active.pop(device_id, None)


def bump_request_count() -> None:
    global _request_count
    with _stats_lock:
        _request_count += 1


def bump_ws_count(delta: int) -> None:
    global _ws_count
    with _stats_lock:
        _ws_count = max(0, _ws_count + delta)


def status_snapshot() -> Dict[str, Any]:
    """状态面板快照（P0-4）：在线设备/活跃 WS/请求计数/DB 大小/版本。"""
    _flush_active()
    now = time.time()
    conn = _get_conn()
    devices: list[Dict[str, Any]] = []
    online_count = 0
    try:
        rows = conn.execute(
            "SELECT device_id, device_name, ip, workspace, first_seen, last_seen "
            "FROM devices "
            "ORDER BY last_seen DESC"
        ).fetchall()
        for r in rows:
            try:
                last = datetime.strptime(
                    r["last_seen"], "%Y-%m-%d %H:%M:%S"
                ).timestamp()
            except ValueError:  # noqa: BLE001
                last = now
            online = (now - last) <= ONLINE_WINDOW
            if online:
                online_count += 1
            devices.append({
                "device_id": r["device_id"],
                "device_name": r["device_name"],
                "ip": r["ip"],
                "first_seen": r["first_seen"],
                "workspace": r["workspace"] if "workspace" in r.keys() else "shared",
                "last_seen": r["last_seen"],
                "online": online,
            })
    finally:
        conn.close()

    db_size = 0
    try:
        p = _db_path()
        if p.exists():
            db_size = p.stat().st_size
    except OSError:  # noqa: BLE001
        pass

    from core.main import APP_VERSION

    version = APP_VERSION

    with _stats_lock:
        req_count = _request_count
        ws_count = _ws_count

    return {
        "online_devices": online_count,
        "devices": devices,
        "active_ws": ws_count,
        "requests": req_count,
        "db_size_bytes": db_size,
        "version": version,
        "online_window_seconds": ONLINE_WINDOW,
    }


# ---------------------------------------------------------------------------
# HTTP 端点（Token 门禁）
# ---------------------------------------------------------------------------


@router.post("/device/register")
async def device_register(
    payload: DeviceRegisterReq,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """设备注册/改名（幂等；刷新在线状态）。"""
    result = register_device(
        payload.device_id, payload.device_name, ip=_client_ip(claims),
        workspace=payload.workspace,
    )
    return ok(result)


@router.post("/device/heartbeat")
async def device_heartbeat(
    payload: DeviceHeartbeatReq,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """设备心跳（在线保活；未注册自动注册）。"""
    result = heartbeat_device(
        payload.device_id, payload.device_name, ip=_client_ip(claims),
        workspace=payload.workspace,
    )
    return ok(result)


@router.get("/status")
async def status(
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """状态面板（P0-4）：在线设备/活跃 WS/请求计数/DB 大小/版本。"""
    return ok(status_snapshot())


def _client_ip(claims: Dict[str, Any]) -> str:
    return str(claims.get("ip") or "")
