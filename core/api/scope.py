"""P0：工作区作用域管理——私有 → 共享提升 + 冲突裁决队列。

对应社区痛点（mneme #170/#177）：自动 scope 过宽后缺少人工提升入口。
团队场景：成员把个人 workspace 笔记提升到 shared 团队知识库；
同 key 不同 value 时进入冲突队列，由管理员裁决。
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core.api_response import fail, ok
from core.config import get_settings
from core.security.token_gate import require_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/scope", tags=["scope", "teams"])

_lock = threading.Lock()


def _db_path() -> Path:
    settings = get_settings()
    cfg = settings.databases.get("main", {})
    if cfg.get("engine") == "sqlite":
        return Path(cfg.get("path", "./data/ddw_main.db")).resolve()
    return Path("./data/ddw_main.db").resolve()


def _conn() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error:  # noqa: BLE001
        pass
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scope_promotions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_workspace TEXT NOT NULL,
            target_workspace TEXT NOT NULL DEFAULT 'shared',
            layer TEXT NOT NULL,
            key TEXT NOT NULL,
            source_value TEXT NOT NULL,
            target_value TEXT,
            status TEXT NOT NULL DEFAULT 'pending',  -- pending|approved|conflict|rejected
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            resolved_at TEXT,
            resolution TEXT
        )
        """
    )
    conn.commit()
    return conn


class PromoteReq(BaseModel):
    layer: str = Field(..., description="user|notes")
    key: str = Field(..., min_length=1, max_length=200)
    source_workspace: str = Field(..., min_length=1, max_length=32)
    target_workspace: str = Field("shared", max_length=32)
    value: Optional[str] = None  # 缺省从源读取


class ResolveReq(BaseModel):
    action: str = Field(..., description="approve|reject|use_target|use_source")


def _read_source(layer: str, key: str, workspace: str) -> Optional[str]:
    from core.knowledge import get_conn, close_conn

    conn = get_conn()
    try:
        if layer == "user":
            row = conn.execute(
                "SELECT value FROM memory_user WHERE workspace=? AND key=?",
                (workspace, key),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT value FROM memory_notes WHERE workspace=? AND key=?",
                (workspace, key),
            ).fetchone()
        return row["value"] if row else None
    finally:
        close_conn(conn)


def _read_target(layer: str, key: str, workspace: str) -> Optional[str]:
    return _read_source(layer, key, workspace)


def _write_target(layer: str, key: str, value: str, workspace: str) -> None:
    if layer == "user":
        from core.knowledge import memory_user_put

        memory_user_put(key, value, workspace=workspace)
    else:
        from core.knowledge import memory_note_put

        memory_note_put(key, value, source="scope-promote", workspace=workspace)


def promote(
    layer: str,
    key: str,
    source_workspace: str,
    target_workspace: str = "shared",
    value: Optional[str] = None,
) -> Dict[str, Any]:
    """提升一条记忆到目标工作区；冲突则入队待裁决。"""
    layer = layer if layer in ("user", "notes") else "notes"
    if not value:
        value = _read_source(layer, key, source_workspace)
    if not value:
        return {"ok": False, "note": "source entry not found"}

    existing = _read_target(layer, key, target_workspace)
    with _lock:
        conn = _conn()
        try:
            if existing is not None and existing != value:
                cur = conn.execute(
                    "INSERT INTO scope_promotions "
                    "(source_workspace, target_workspace, layer, key, "
                    " source_value, target_value, status) "
                    "VALUES (?,?,?,?,?,?,'pending')",
                    (source_workspace, target_workspace, layer, key, value, existing),
                )
                conn.commit()
                return {
                    "ok": True,
                    "status": "conflict",
                    "promotion_id": cur.lastrowid,
                    "note": "target already has a different value; queued for review",
                }
            if existing == value:
                return {"ok": True, "status": "noop", "note": "target already identical"}
            _write_target(layer, key, value, target_workspace)
            cur = conn.execute(
                "INSERT INTO scope_promotions "
                "(source_workspace, target_workspace, layer, key, "
                " source_value, target_value, status, resolved_at, resolution) "
                "VALUES (?,?,?,?,?,?, 'approved', datetime('now'), 'auto')",
                (source_workspace, target_workspace, layer, key, value, None),
            )
            conn.commit()
            return {"ok": True, "status": "approved", "promotion_id": cur.lastrowid}
        finally:
            conn.close()


def list_conflicts(status: str = "pending") -> List[Dict[str, Any]]:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM scope_promotions WHERE status=? ORDER BY id DESC LIMIT 100",
            (status,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def resolve(promotion_id: int, action: str) -> Dict[str, Any]:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM scope_promotions WHERE id=?", (promotion_id,)
        ).fetchone()
        if row is None:
            return {"ok": False, "note": "promotion not found"}
        if action == "approve" or action == "use_source":
            _write_target(row["layer"], row["key"], row["source_value"], row["target_workspace"])
            status, resolution = "approved", action
        elif action == "use_target":
            status, resolution = "approved", "use_target"
        elif action == "reject":
            status, resolution = "rejected", "reject"
        else:
            return {"ok": False, "note": "invalid action"}
        conn.execute(
            "UPDATE scope_promotions SET status=?, resolution=?, "
            "resolved_at=datetime('now') WHERE id=?",
            (status, resolution, promotion_id),
        )
        conn.commit()
        return {"ok": True, "status": status, "promotion_id": promotion_id}
    finally:
        conn.close()


@router.post("/promote")
async def promote_endpoint(
    payload: PromoteReq,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    result = promote(
        payload.layer,
        payload.key,
        payload.source_workspace,
        payload.target_workspace,
        payload.value,
    )
    if not result.get("ok"):
        return fail(result.get("note", "promote failed"))
    return ok(result)


@router.get("/conflicts")
async def conflicts_endpoint(
    status: str = "pending",
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    return ok({"items": list_conflicts(status), "status": status})


@router.post("/conflicts/{promotion_id}/resolve")
async def resolve_endpoint(
    promotion_id: int,
    payload: ResolveReq,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    result = resolve(promotion_id, payload.action)
    if not result.get("ok"):
        return fail(result.get("note", "resolve failed"))
    return ok(result)
