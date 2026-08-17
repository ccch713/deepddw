"""R4-0 / R4-1（DSH for Teams）：部署模式 + 成员系统。

- R4-0 部署模式：solo|family|team（config deployment.mode + env）；launcher
  首次运行选择写入配置；未配置默认 solo（v0.3.0 行为不变）。
- R4-1 成员系统（family/team 模式启用）：
  - 管理员生成邀请码（可设过期/最大次数）；新设备输入邀请码绑定成员；
  - family 模式管理员可直接添加成员（免邀请码）；team 模式邀请码制；
  - 成员列表/吊销；SQLite members 表；TokenGateASGI 语义不变（成员层叠加）。
"""

from __future__ import annotations

import logging
import secrets
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core.api_response import ok
from core.config import get_deployment_mode, get_settings
from core.security.token_gate import require_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["teams", "members"])

# 邀请码字符集/长度
_INVITE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 去易混 I/O/0/1
_INVITE_LEN = 8
_MEMBER_ID_RE = __import__("re").compile(r"^[A-Za-z0-9_\-]{4,64}$")

_members_lock = threading.Lock()


def _db_path() -> Path:
    settings = get_settings()
    cfg = settings.databases.get("main", {})
    if cfg.get("engine") == "sqlite":
        return Path(cfg.get("path", "./data/ddw_main.db")).resolve()
    return Path("./data/ddw_main.db").resolve()


def _get_conn() -> sqlite3.Connection:
    """连接（测试可通过 monkeypatch _db_path 覆盖数据库路径）。"""
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error:  # noqa: BLE001
        pass
    _ensure_members_table(conn)
    return conn


def _ensure_members_table(conn) -> None:  # noqa: ANN001
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS members (
            member_id    TEXT PRIMARY KEY,
            display_name TEXT NOT NULL DEFAULT '',
            role         TEXT NOT NULL DEFAULT 'member',   -- admin / member
            device_ids   TEXT NOT NULL DEFAULT '[]',        -- JSON 数组
            invite_code  TEXT NOT NULL DEFAULT '',
            invited_by   TEXT NOT NULL DEFAULT '',
            registered_at TEXT NOT NULL,
            revoked      INTEGER NOT NULL DEFAULT 0,
            workspace    TEXT NOT NULL DEFAULT 'shared'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS invites (
            invite_code TEXT PRIMARY KEY,
            note        TEXT NOT NULL DEFAULT '',
            max_uses    INTEGER NOT NULL DEFAULT 1,
            used_count  INTEGER NOT NULL DEFAULT 0,
            expires_at  INTEGER NOT NULL,
            created_at  TEXT NOT NULL
        )
        """
    )
    conn.commit()


# ---------------------------------------------------------------------------
# 成员逻辑
# ---------------------------------------------------------------------------


def _gen_invite() -> str:
    return "".join(secrets.choice(_INVITE_CHARS) for _ in range(_INVITE_LEN))


def members_enabled() -> bool:
    """成员系统仅在 family/team 模式启用（solo 关闭）。"""
    return get_deployment_mode() in ("family", "team")


def create_invite(
    note: str = "", max_uses: int = 1, expires_hours: int = 168,
) -> Dict[str, Any]:
    """管理员生成邀请码（可设过期/最大次数；默认 7 天 1 次）。"""
    code = _gen_invite()
    expires_at = datetime.now().timestamp() + expires_hours * 3600
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO invites (invite_code, note, max_uses, used_count, "
            "expires_at, created_at) VALUES (?, ?, ?, 0, ?, datetime('now'))",
            (code, (note or "")[:100], max(1, int(max_uses)),
             int(expires_at)),
        )
        conn.commit()
        return {"ok": True, "invite_code": code,
                "expires_at": int(expires_at), "max_uses": max(1, int(max_uses))}
    except Exception as exc:  # noqa: BLE001
        logger.warning("invite create degraded: %s", exc)
        return {"ok": False, "degraded": True, "note": str(exc)}
    finally:
        conn.close()


def register_member(
    invite_code: str, display_name: str = "", device_id: str = "",
) -> Dict[str, Any]:
    """新设备输入邀请码 → 绑定成员（生成 member_id；失败返回明确原因）。"""
    code = (invite_code or "").strip().upper()
    if not code:
        return {"ok": False, "note": "缺少邀请码"}
    conn = _get_conn()
    try:
        inv = conn.execute(
            "SELECT invite_code, max_uses, used_count, expires_at "
            "FROM invites WHERE invite_code=?", (code,)
        ).fetchone()
        if inv is None:
            return {"ok": False, "note": "邀请码不存在"}
        if int(inv["used_count"]) >= int(inv["max_uses"]):
            return {"ok": False, "note": "邀请码已达最大使用次数"}
        if float(inv["expires_at"]) < time.time():
            return {"ok": False, "note": "邀请码已过期"}
        # 生成 member_id（8 位短码，防猜）
        member_id = "m-" + "".join(secrets.choice(_INVITE_CHARS) for _ in range(8))
        conn.execute(
            "INSERT INTO members (member_id, display_name, role, device_ids, "
            "invite_code, registered_at) VALUES (?, ?, 'member', ?, ?, datetime('now'))",
            (member_id, (display_name or "")[:40], f'["{device_id}"]', code),
        )
        conn.execute(
            "UPDATE invites SET used_count=used_count+1 WHERE invite_code=?",
            (code,),
        )
        conn.commit()
        return {"ok": True, "member_id": member_id, "display_name": display_name or member_id}
    except Exception as exc:  # noqa: BLE001
        logger.warning("member register degraded: %s", exc)
        return {"ok": False, "degraded": True, "note": str(exc)}
    finally:
        conn.close()


def add_member_direct(
    display_name: str = "", device_id: str = "",
) -> Dict[str, Any]:
    """family 模式：管理员直接添加成员（免邀请码——家人互信）。"""
    member_id = "m-" + "".join(secrets.choice(_INVITE_CHARS) for _ in range(8))
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO members (member_id, display_name, role, device_ids, "
            "registered_at) VALUES (?, ?, 'member', ?, datetime('now'))",
            (member_id, (display_name or "")[:40], f'["{device_id}"]'),
        )
        conn.commit()
        return {"ok": True, "member_id": member_id, "display_name": display_name or member_id}
    except Exception as exc:  # noqa: BLE001
        logger.warning("member add degraded: %s", exc)
        return {"ok": False, "degraded": True, "note": str(exc)}
    finally:
        conn.close()


def list_members() -> Dict[str, Any]:
    """成员列表（含在线/吊销状态）。"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT member_id, display_name, role, device_ids, invite_code, "
            "registered_at, revoked FROM members ORDER BY revoked, registered_at"
        ).fetchall()
        return {"results": [dict(r) for r in rows], "degraded": False}
    except Exception as exc:  # noqa: BLE001
        logger.warning("member list degraded: %s", exc)
        return {"results": [], "degraded": True, "note": str(exc)}
    finally:
        conn.close()


def revoke_member(member_id: str) -> Dict[str, Any]:
    """吊销成员（revoked=1；不影响历史数据，仅拒绝新登录/写入）。"""
    conn = _get_conn()
    try:
        cur = conn.execute(
            "UPDATE members SET revoked=1 WHERE member_id=?",
            (member_id,),
        )
        conn.commit()
        if cur.rowcount == 0:
            return {"ok": False, "note": "成员不存在"}
        return {"ok": True, "member_id": member_id}
    except Exception as exc:  # noqa: BLE001
        logger.warning("member revoke degraded: %s", exc)
        return {"ok": False, "degraded": True, "note": str(exc)}
    finally:
        conn.close()


def bind_device_to_member(device_id: str, member_id: str) -> Dict[str, Any]:
    """设备 ↔ 成员绑定（重连自动识别；device_id 存成员 device_ids）。"""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT device_ids FROM members WHERE member_id=?", (member_id,)
        ).fetchone()
        if row is None:
            return {"ok": False, "note": "成员不存在"}
        import json as _json

        ids: List[str] = _json.loads(row["device_ids"] or "[]")
        if device_id and device_id not in ids:
            ids.append(device_id)
            conn.execute(
                "UPDATE members SET device_ids=? WHERE member_id=?",
                (_json.dumps(ids), member_id),
            )
            conn.commit()
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        logger.warning("device bind degraded: %s", exc)
        return {"ok": False, "degraded": True, "note": str(exc)}
    finally:
        conn.close()


def member_for_device(device_id: str) -> Optional[Dict[str, Any]]:
    """按设备查成员（重连识别）；无绑定返回 None。"""
    if not device_id:
        return None
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT member_id, display_name, role, device_ids, revoked FROM members"
        ).fetchall()
        for r in rows:
            import json as _json

            try:
                ids = _json.loads(r["device_ids"] or "[]")
            except Exception:  # noqa: BLE001
                ids = []
            if device_id in ids and not r["revoked"]:
                return dict(r)
        return None
    except Exception:  # noqa: BLE001
        return None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# R4-2（DSH for Teams）：用户级隔离——namespace 命名规则
# ---------------------------------------------------------------------------

# 隔离层级枚举（IsolationLevel 接口，商业版可扩展）
ISOLATION_LEVELS: Dict[str, Dict[str, Any]] = {
    "solo":   {"shared_prefix": "", "member_prefix": "", "has_distill": False},
    "family": {"shared_prefix": "family:default", "member_prefix": "member:",
               "has_distill": True},
    "team":   {"shared_prefix": "team:default", "member_prefix": "member:",
               "has_distill": True},
}


def resolve_namespace(
    mode: str = "solo", member_id: str = "", is_shared: bool = False,
) -> str:
    """R4-2：按 mode/member_id 解析实际 workspace 参数（传给 memory 函数）。

    - solo → 'shared'（全部 v0.3.0 行为）
    - family/team 共享空间 → 'family:default' / 'team:default'
    - family/team 个人空间 → 'member:<id>'
    - 无 member_id 回退 shared（旧客户端兼容）
    """
    lvl = ISOLATION_LEVELS.get(mode, ISOLATION_LEVELS["solo"])
    if not lvl["shared_prefix"]:  # solo
        return "shared"
    if is_shared:
        return lvl["shared_prefix"]
    if member_id and _MEMBER_ID_RE.match(member_id):
        return f"{lvl['member_prefix']}{member_id}"
    return "shared"  # 无 member_id 回退 shared（向后兼容）



# ---------------------------------------------------------------------------
# HTTP 端点（Token 门禁；成员层叠加在 Token 之上，不改 TokenGateASGI）
# ---------------------------------------------------------------------------


class ModeReq(BaseModel):
    mode: str = Field(..., min_length=1, max_length=16)


class InviteReq(BaseModel):
    note: str = Field(default="", max_length=100)
    max_uses: int = Field(default=1, ge=1, le=1000)
    expires_hours: int = Field(default=168, ge=1, le=8760)


class MemberRegisterReq(BaseModel):
    invite_code: str = Field(..., min_length=4, max_length=16)
    display_name: str = Field(default="", max_length=40)
    device_id: str = Field(default="", max_length=64)


class MemberAddReq(BaseModel):
    display_name: str = Field(default="", max_length=40)
    device_id: str = Field(default="", max_length=64)


class MemberRevokeReq(BaseModel):
    member_id: str = Field(..., min_length=4, max_length=64)


class DeviceBindReq(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=64)
    member_id: str = Field(..., min_length=4, max_length=64)


@router.get("/deployment/mode")
async def get_mode(
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """当前部署模式 + 是否已配置（launcher 首次运行据此显示选择器）。"""
    from core.config import deployment_mode_configured

    return ok({
        "mode": get_deployment_mode(),
        "configured": deployment_mode_configured(),
        "modes": ["solo", "family", "team"],
    })


@router.post("/deployment/mode")
async def set_mode(
    payload: ModeReq,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """设置部署模式（写 deployment.yaml；重启生效，不支持热切换）。"""
    from core.config import set_deployment_mode

    return ok(set_deployment_mode(payload.mode))


@router.post("/invite/create")
async def invite_create(
    payload: InviteReq,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """管理员生成邀请码（仅 family/team 模式）。"""
    if not members_enabled():
        return ok({"ok": False, "note": "成员系统未启用（当前 solo 模式）"})
    return ok(create_invite(payload.note, payload.max_uses, payload.expires_hours))


@router.post("/member/register")
async def member_register(
    payload: MemberRegisterReq,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """新设备输入邀请码 → 绑定成员（team 模式）。"""
    if not members_enabled():
        return ok({"ok": False, "note": "成员系统未启用（当前 solo 模式）"})
    return ok(register_member(payload.invite_code, payload.display_name, payload.device_id))


@router.post("/member/add")
async def member_add(
    payload: MemberAddReq,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """直接添加成员（family 模式免邀请码；team 模式建议走邀请码）。"""
    if not members_enabled():
        return ok({"ok": False, "note": "成员系统未启用（当前 solo 模式）"})
    return ok(add_member_direct(payload.display_name, payload.device_id))


@router.get("/member/list")
async def member_list(
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """成员列表（family/team）。"""
    if not members_enabled():
        return ok({"results": [], "note": "成员系统未启用（solo 模式）"})
    return ok(list_members())


@router.post("/member/revoke")
async def member_revoke(
    payload: MemberRevokeReq,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """吊销成员。"""
    return ok(revoke_member(payload.member_id))


@router.post("/device/bind-member")
async def device_bind(
    payload: DeviceBindReq,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """设备 ↔ 成员绑定（launcher 注册后调用；重连自动识别）。"""
    return ok(bind_device_to_member(payload.device_id, payload.member_id))


@router.get("/device/member")
async def device_member(
    device_id: str,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """按设备查绑定成员（重连识别）。"""
    m = member_for_device(device_id)
    return ok({"member": m} if m else {"member": None})


# ---------------------------------------------------------------------------
# R4-5（DSH for Teams）：管理员面板 API（solo 不显示；family 简化；team 完整）
# ---------------------------------------------------------------------------


@router.get("/admin/stats")
async def admin_stats(
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """管理员统计（solo 不可用；family 简化；team 完整）。

    返回：mode、成员总数/在线/吊销、记忆 KB 统计、蒸馏状态。
    """
    mode = get_deployment_mode()
    if mode == "solo":
        return ok({"ok": False, "note": "管理面板仅在 family/team 模式可用"})
    members = list_members().get("results", [])
    from core.knowledge import memory_logs_recent

    user_ws = "family:default" if mode == "family" else "team:default"
    stats = {
        "mode": mode,
        "members": {
            "total": len(members),
            "active": sum(1 for m in members if not m.get("revoked")),
            "revoked": sum(1 for m in members if m.get("revoked")),
        },
        "shared_memory": {
            "logs_3d": len(memory_logs_recent(3, workspace=user_ws).get("results", [])),
        },
    }
    return ok(stats)


@router.post("/admin/distill")
async def admin_distill(
    payload: Any = None,  # DistillReq（延迟导入避免循环；None → 默认）
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """管理员手动触发蒸馏（solo 不可用）。"""
    from core.api.distill import DistillReq, get_distillation_targets

    payload = payload if isinstance(payload, DistillReq) else DistillReq()
    mode = get_deployment_mode()
    if mode == "solo":
        return ok({"ok": False, "note": "蒸馏功能仅在 family/team 模式可用"})

    targets = get_distillation_targets(mode)
    if not targets:
        return ok({"ok": False, "note": f"无蒸馏目标（mode={mode}）"})
    result = await targets[0].distill_fn(recent_days=payload.recent_days)
    return ok(result)
