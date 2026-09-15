"""会话隐私（无痕模式）：本会话不写记忆，仍可读。

团队共用服务器时的隐私刚需——用户可对当前会话开启无痕，
记忆写入/自动沉淀被拦截；检索/注入读取保持默认行为。
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

# session_id -> expire_ts（与 workspace 映射同 TTL 约定：30 分钟）
_PRIVACY_TTL = 1800
_privacy: Dict[str, float] = {}
_privacy_lock = threading.Lock()

# 请求级线程局部：chat 处理期间可绑定 conversation/session
_local = threading.local()


def set_incognito(session_id: str, enabled: bool = True, ttl: int = _PRIVACY_TTL) -> Dict[str, Any]:
    """开启/关闭某会话的无痕模式。"""
    sid = (session_id or "").strip()
    if not sid:
        return {"ok": False, "note": "invalid session_id"}
    with _privacy_lock:
        if enabled:
            _privacy[sid] = time.time() + ttl
        else:
            _privacy.pop(sid, None)
    return {"ok": True, "session_id": sid, "incognito": enabled}


def is_incognito(session_id: Optional[str]) -> bool:
    """会话是否处于无痕模式（未绑定/过期 → False）。"""
    if not session_id:
        return bool(getattr(_local, "force_incognito", False))
    now = time.time()
    with _privacy_lock:
        expire = _privacy.get(session_id)
        if expire is None:
            return bool(getattr(_local, "force_incognito", False))
        if now > expire:
            _privacy.pop(session_id, None)
            return False
        return True


def set_request_incognito(enabled: bool) -> None:
    """当前线程请求级无痕开关（chat payload.privacy 用）。"""
    _local.force_incognito = bool(enabled)


def clear_request_incognito() -> None:
    _local.force_incognito = False


def reset_privacy_map() -> None:
    """测试/维护用。"""
    with _privacy_lock:
        _privacy.clear()
    clear_request_incognito()


def privacy_status(session_id: Optional[str] = None) -> Dict[str, Any]:
    with _privacy_lock:
        active = bool(is_incognito(session_id))
        return {
            "session_id": session_id,
            "incognito": active,
            "active_sessions": len(_privacy),
        }
