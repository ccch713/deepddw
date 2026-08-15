"""DDW 授权换码广播状态机（P2）+ 完整性保护（P3 对抗性验证加固）。

业务机制（已定案）：
- 客户加购/升级 → 经销商发新授权码 → 客户激活新码（license_cache.json 的
  license_key 变化）→ 本模块检测变化并广播：旧码进入 7 天倒计时（宽限期=客户
  切换工期），期间旧码仍可用但提示"授权即将更新"；超期后旧码失效，数据同步
  被拒（"授权已更新，请联系经销商获取新授权码"）。

license_state.json 结构（P3 起带完整性保护）：
    {
      "data": {
        "active_license_key": "LIC-OLD-001",
        "superseded_by": "LIC-NEW-002",
        "superseded_at": "2026-08-14T00:00:00+00:00",
        "grace_ends_at": "2026-08-21T00:00:00+00:00"
      },
      "sig": "<hmac-sha256 hex>"
    }

完整性保护（P3）：
- ``sig`` = HMAC-SHA256(data 的规范 JSON)，密钥来自环境变量
  ``DDW_LICENSE_STATE_KEY``（部署端注入，与 license 公钥并列的部署配置）。
- 配置密钥后：篡改 state 内容 → 验签失败 → 同步拦截 fail-closed
  （"授权状态文件校验失败（可能被篡改），拒绝同步"）。
- 未配置密钥：state 以无保护模式运行（打 warning），换码广播的防篡改
  保护未启用（部署文档要求配置）。

写入一律原子（临时文件 + os.replace）+ 进程级 fcntl 锁。
时间统一使用 ``datetime.timezone.utc``。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# 换码宽限期（天）：旧码倒计时
SUPERSEDE_GRACE_DAYS = 7

# 状态文件 HMAC 密钥环境变量（部署端注入；未配置 → 无保护模式 + 告警）
STATE_KEY_ENV = "DDW_LICENSE_STATE_KEY"

# 默认状态文件（与 license.cache_path 同目录，见 _state_path）
LICENSE_STATE_FILE_DEFAULT = "./data/license_state.json"

# 状态完整性：ok=签名校验通过 / unsigned=未配置密钥或旧格式 / tampered=校验失败
_INTEGRITY_OK = "ok"
_INTEGRITY_UNSIGNED = "unsigned"
_INTEGRITY_TAMPERED = "tampered"

_EMPTY_STATE: Dict[str, Any] = {
    "active_license_key": None,
    "superseded_by": None,
    "superseded_at": None,
    "grace_ends_at": None,
}

_TAMPERED_MESSAGE = "授权状态文件校验失败（可能被篡改），拒绝同步"


def _state_path() -> Path:
    """状态文件路径：与 license.cache_path 同源（同目录 license_state.json）。"""
    try:
        from core.config import get_settings

        raw = get_settings().raw.get("license", {})
        cache = raw.get("cache_path", "./data/license_cache.json")
    except Exception:  # noqa: BLE001  # 配置读取失败用默认
        cache = "./data/license_cache.json"
    return Path(cache).resolve().parent / "license_state.json"


def _license_cache_path() -> Path:
    try:
        from core.config import get_settings

        raw = get_settings().raw.get("license", {})
        cache = raw.get("cache_path", "./data/license_cache.json")
    except Exception:  # noqa: BLE001
        cache = "./data/license_cache.json"
    return Path(cache)


def _state_key() -> str:
    """返回 HMAC 密钥；未配置返回空串（无保护模式）。"""
    return os.environ.get(STATE_KEY_ENV, "").strip()


def _sign_state(data: Dict[str, Any]) -> str:
    """对 state data 计算 HMAC-SHA256 签名（hex）。密钥未配置返回空串。"""
    key = _state_key()
    if not key:
        return ""
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hmac.new(key.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _verify_signature(data: Dict[str, Any], signature: str, key: str) -> bool:
    if not key:
        return False
    expected = hmac.new(
        key.encode("utf-8"),
        json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def _load_raw_state(path: Path) -> Tuple[Dict[str, Any], str]:
    """读取状态文件并判定完整性。

    Returns:
        (state_dict, integrity) — integrity ∈ ok / unsigned / tampered
    """
    if not path.exists():
        return dict(_EMPTY_STATE), _INTEGRITY_OK
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.critical("license_state read failed: %s — treated as tampered", e)
        return dict(_EMPTY_STATE), _INTEGRITY_TAMPERED

    key = _state_key()
    if isinstance(raw, dict) and "data" in raw and "sig" in raw:
        data = raw["data"]
        if not isinstance(data, dict):
            return dict(_EMPTY_STATE), _INTEGRITY_TAMPERED
        merged = dict(_EMPTY_STATE)
        merged.update({k: data.get(k) for k in _EMPTY_STATE if k in data})
        if not key:
            logger.warning(
                "license_state unsigned (DDW_LICENSE_STATE_KEY not set) — "
                "tamper protection disabled"
            )
            return merged, _INTEGRITY_UNSIGNED
        if _verify_signature(merged, raw.get("sig", ""), key):
            return merged, _INTEGRITY_OK
        logger.critical(
            "license_state signature mismatch — file tampered (or key rotated)"
        )
        return merged, _INTEGRITY_TAMPERED

    # 旧格式（P2 无签名顶层字段）：配置密钥后视为不可信
    if key:
        logger.critical(
            "license_state in legacy unsigned format but DDW_LICENSE_STATE_KEY is set "
            "— treated as tampered; delete the file to let the system rebuild it"
        )
        return dict(_EMPTY_STATE), _INTEGRITY_TAMPERED
    logger.warning(
        "license_state in legacy unsigned format (DDW_LICENSE_STATE_KEY not set) — "
        "tamper protection disabled"
    )
    merged = dict(_EMPTY_STATE)
    if isinstance(raw, dict):
        merged.update({k: raw.get(k) for k in _EMPTY_STATE if k in raw})
    return merged, _INTEGRITY_UNSIGNED


def load_license_state(path: Optional[str | Path] = None) -> Dict[str, Any]:
    """读取 license_state.json（不存在/损坏返回空状态，不抛异常）。

    完整性失败（tampered）时返回空状态并记录 critical 日志；
    调用方如需区分请使用 :func:`check_sync_allowed`（其按 tampered 拒绝放行）。
    """
    state_path = Path(path) if path is not None else _state_path()
    state, integrity = _load_raw_state(state_path)
    if integrity == _INTEGRITY_TAMPERED:
        logger.critical(
            "license_state tampered at %s — returning empty state (fail-closed)",
            state_path,
        )
    return state


def _atomic_write(state: Dict[str, Any], path: Optional[str | Path] = None) -> Path:
    """原子写入状态文件：进程锁 + 同目录临时文件 + os.replace。

    新格式：{"data": state, "sig": HMAC-SHA256(state)}；未配置密钥时 sig 为空串
    （无保护模式，写入后打 warning 提示配置 DDW_LICENSE_STATE_KEY）。
    """
    state_path = Path(path) if path is not None else _state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)

    if not _state_key():
        logger.warning(
            "license_state written WITHOUT signature (DDW_LICENSE_STATE_KEY not set) "
            "— tamper protection disabled"
        )
    signature = _sign_state(state)
    payload = {"data": state, "sig": signature}

    try:
        import fcntl

        # 进程级锁（防多 worker 并发写；Windows 无 fcntl，走降级路径）
        with open(state_path, "a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                _write_payload_atomic(payload, state_path)
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
    except ImportError:
        _write_payload_atomic(payload, state_path)

    return state_path


def _write_payload_atomic(payload: Dict[str, Any], state_path: Path) -> None:
    fd, tmp_name = tempfile.mkstemp(
        prefix=".license_state.", suffix=".tmp", dir=str(state_path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, state_path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_active(
    license_key: str, path: Optional[str | Path] = None
) -> Dict[str, Any]:
    """记录当前生效码（首次激活或新码回归时清除替换记录）。"""
    state = load_license_state(path)
    state.update({
        "active_license_key": license_key,
        "superseded_by": None,
        "superseded_at": None,
        "grace_ends_at": None,
    })
    _atomic_write(state, path)
    return state


def replace_state(
    state: Dict[str, Any], path: Optional[str | Path] = None
) -> Dict[str, Any]:
    """用权威 state（如 Broker 拉取结果）原子覆盖本机状态（P4）。

    仅合并本状态机的 4 个字段，忽略其它字段；带 HMAC 签名写入。
    幂等：state 与本机一致时仍会重写（调用方应自行比对避免无谓写入）。
    """
    merged = dict(_EMPTY_STATE)
    if isinstance(state, dict):
        merged.update({k: state.get(k) for k in _EMPTY_STATE if k in state})
    _atomic_write(merged, path)
    return merged


def supersede(
    old_key: str,
    new_key: str,
    grace_days: int = SUPERSEDE_GRACE_DAYS,
    path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """记录换码：旧码进入宽限期倒计时。"""
    if grace_days < 0:
        raise ValueError("grace_days 必须 >= 0")
    state = load_license_state(path)
    state.update({
        "active_license_key": old_key,
        "superseded_by": new_key,
        "superseded_at": _utc_now_iso(),
        "grace_ends_at": (
            datetime.now(timezone.utc) + timedelta(days=grace_days)
        ).isoformat(),
    })
    _atomic_write(state, path)
    logger.warning(
        "license superseded: old=%s superseded_by=%s grace_ends_at=%s",
        old_key,
        new_key,
        state["grace_ends_at"],
    )
    return state


def sync_license_state(
    license_key: Optional[str] = None,
    path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """换码广播入口：检测 license_cache.json 的 license_key 变化并更新状态。

    - 当前码 == state.active → 无变化
    - 当前码 == state.superseded_by → 新码回归：清除替换记录（active=新码）
    - 当前码 != state.active（且非 superseded_by）→ 记录旧码 superseded + 倒计时
    - state 无 active → 首次记录

    Args:
        license_key: 显式传入当前码；缺省从 license_cache.json 读取。
    """
    if license_key is None:
        try:
            cache = _license_cache_path()
            if not cache.exists():
                return load_license_state(path)
            data = json.loads(cache.read_text(encoding="utf-8"))
            license_key = (data or {}).get("license_key")
        except (json.JSONDecodeError, OSError):
            return load_license_state(path)
    if not license_key:
        return load_license_state(path)

    state_path = Path(path) if path is not None else _state_path()
    state, integrity = _load_raw_state(state_path)
    if integrity == _INTEGRITY_TAMPERED:
        # 状态被篡改：拒绝覆盖（避免攻击者通过改状态文件诱导写回），
        # 由拦截层 fail-closed。
        logger.critical(
            "sync_license_state aborted: license_state tampered at %s", state_path
        )
        return state

    active = state.get("active_license_key")

    if active == license_key:
        return state
    if state.get("superseded_by") == license_key:
        # 新码回归：它就是当前生效码，清除替换记录
        logger.info(
            "license renewed: new_code=%s cleared supersede record", license_key
        )
        return record_active(license_key, path)
    if active:
        # 换码：旧码 superseded
        return supersede(active, license_key, path=path)
    return record_active(license_key, path)


def get_supersede_status(path: Optional[str | Path] = None) -> Dict[str, Any]:
    """返回换码状态（含宽限判定），供日志/接口/拦截使用。"""
    state = load_license_state(path)
    grace_ends_at = state.get("grace_ends_at")
    grace_expired = False
    grace_days_left: Optional[int] = None
    if state.get("superseded_by") and grace_ends_at:
        try:
            ends = datetime.fromisoformat(grace_ends_at)
            now = datetime.now(timezone.utc)
            if ends.tzinfo is None:
                ends = ends.replace(tzinfo=timezone.utc)
            grace_expired = now > ends
            remaining = (ends - now).total_seconds()
            grace_days_left = max(0, int(remaining // 86400))
        except (ValueError, TypeError):
            grace_expired = True  # 时间格式异常按已失效处理（安全方向）
    return {
        "superseded": bool(state.get("superseded_by")),
        "active_license_key": state.get("active_license_key"),
        "superseded_by": state.get("superseded_by"),
        "superseded_at": state.get("superseded_at"),
        "grace_ends_at": grace_ends_at,
        "grace_expired": grace_expired,
        "grace_days_left": grace_days_left,
    }


def check_sync_allowed(
    license_key: Optional[str] = None,
    path: Optional[str | Path] = None,
) -> Tuple[bool, str]:
    """数据同步授权校验（拦截点判定，P3 起含状态文件完整性校验）。

    - 状态文件被篡改（签名校验失败）→ 拒绝："授权状态文件校验失败（可能被篡改）"
    - 无替换记录 / 当前码是新码 / 码不在状态表中 → 放行
    - 当前码是已被替换的旧码：
        - 宽限期内 → 放行但提示"授权即将更新"（日志警告）
        - 超期 → 拒绝："授权已更新，请联系经销商获取新授权码"
    """
    # P4 第二批（数据同步捎带广播）：每次数据同步校验前，先确保本机 state
    # 为 Broker 权威值（TTL 内 no-op；Broker 不可达回退本地缓存）。
    # 函数内延迟 import 避免 license_broker ↔ license_state 循环依赖。
    try:
        from core.utils.license_broker import sync_from_broker

        sync_from_broker()
    except Exception:  # noqa: BLE001  # 未配置/不可达均不影响既有判定
        pass
    if license_key is None:
        try:
            cache = _license_cache_path()
            if not cache.exists():
                return True, ""
            data = json.loads(cache.read_text(encoding="utf-8"))
            license_key = (data or {}).get("license_key")
        except (json.JSONDecodeError, OSError):
            return True, ""

    state_path = Path(path) if path is not None else _state_path()
    state, integrity = _load_raw_state(state_path)
    if integrity == _INTEGRITY_TAMPERED:
        return False, _TAMPERED_MESSAGE
    if integrity == _INTEGRITY_UNSIGNED:
        logger.warning(
            "sync check on unsigned license_state (DDW_LICENSE_STATE_KEY not set) — "
            "tamper protection disabled"
        )

    if not state.get("superseded_by"):
        return True, ""
    if license_key == state.get("superseded_by"):
        return True, ""
    if license_key != state.get("active_license_key"):
        # 未知码：不误伤（按放行处理），记日志
        logger.warning("sync by unknown license_key=%s", license_key)
        return True, ""

    status = get_supersede_status(path)
    if status["grace_expired"]:
        return False, "授权已更新，请联系经销商获取新授权码"
    logger.warning(
        "sync with superseded license: license_key=%s superseded_by=%s "
        "grace_ends_at=%s — 授权即将更新",
        license_key,
        state.get("superseded_by"),
        state.get("grace_ends_at"),
    )
    return True, "授权即将更新"


__all__ = [
    "SUPERSEDE_GRACE_DAYS",
    "STATE_KEY_ENV",
    "LICENSE_STATE_FILE_DEFAULT",
    "load_license_state",
    "record_active",
    "supersede",
    "replace_state",
    "sync_license_state",
    "get_supersede_status",
    "check_sync_allowed",
]
