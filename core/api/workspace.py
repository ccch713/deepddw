"""P1-1（multidevice）：工作区隔离——Mcp-Session-Id → workspace 映射。

- 设备在启动页选 workspace（默认 ``shared``，向后兼容）；
- 网关维护 session→workspace 映射（内存 + 过期回收）；MCP 调用按会话
  解析 workspace，记忆读写自动限定该 workspace；
- 未绑定会话 → 默认 ``shared``（旧客户端零影响）；
- 共享 `shared` 与旧行为完全一致；非 shared 工作区之间记忆互不可见。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core.api_response import ok
from core.security.token_gate import require_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workspace", tags=["multidevice", "workspace"])

# 默认工作区（与旧行为一致）
DEFAULT_WORKSPACE = "shared"

# 会话映射 TTL（秒）：会话 30 分钟无请求即过期（与 MCP session idle 一致）
_SESSION_TTL = 1800
# 工作区名合法性：字母数字下划线连字符，长度 ≤32
_WORKSPACE_RE = __import__("re").compile(r"^[A-Za-z0-9_\-]{1,32}$")

# session_id -> (workspace, expire_ts)
_sessions: Dict[str, tuple] = {}
_sessions_lock = threading.Lock()


def _valid_workspace(name: str) -> bool:
    return bool(name and _WORKSPACE_RE.match(name))


def bind_session(session_id: str, workspace: str) -> Dict[str, Any]:
    """绑定 Mcp-Session-Id → workspace（幂等；未绑定会话自动建）。

    返回 ok/workspace；workspace 非法 → ok=False（拒绝绑定，保持默认 shared）。
    """
    session_id = (session_id or "").strip()
    workspace = (workspace or "").strip() or DEFAULT_WORKSPACE
    if not _valid_workspace(workspace):
        return {"ok": False, "note": "invalid workspace (a-z0-9_- max 32)"}
    if not session_id:
        return {"ok": False, "note": "invalid session_id"}
    with _sessions_lock:
        _sessions[session_id] = (workspace, time.time() + _SESSION_TTL)
    return {"ok": True, "session_id": session_id, "workspace": workspace}


def get_workspace(session_id: Optional[str]) -> str:
    """按会话取 workspace；未绑定/过期 → DEFAULT_WORKSPACE（旧客户端零影响）。"""
    if not session_id:
        return DEFAULT_WORKSPACE
    now = time.time()
    with _sessions_lock:
        hit = _sessions.get(session_id)
        if hit is None:
            return DEFAULT_WORKSPACE
        workspace, expire = hit
        if now > expire:
            _sessions.pop(session_id, None)
            return DEFAULT_WORKSPACE
        return workspace


def unbind_session(session_id: str) -> None:
    with _sessions_lock:
        _sessions.pop(session_id, None)


def reset_workspace_map() -> None:
    """测试/维护用：清空会话映射。"""
    with _sessions_lock:
        _sessions.clear()


# ---------------------------------------------------------------------------
# HTTP 端点（Token 门禁）
# ---------------------------------------------------------------------------


class WorkspaceBindReq(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    workspace: str = Field(..., min_length=1, max_length=32)


@router.post("/bind")
async def bind(
    payload: WorkspaceBindReq,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """绑定 MCP 会话 → 工作区（设备进工作台后调用一次）。"""
    return ok(bind_session(payload.session_id, payload.workspace))


@router.get("/current")
async def current(
    session_id: str,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """查询某会话当前工作区（未绑定 → shared）。"""
    return ok({"session_id": session_id, "workspace": get_workspace(session_id)})
