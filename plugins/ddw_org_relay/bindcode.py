"""绑定码签发与校验（bindcode-v1 §2）。

码格式：``DDWORG-<b64url(org_id|exp_ts|nonce)>.<hmac16>``

- payload = ``org_id|exp_ts|nonce``，UTF-8，b64url 去 padding；
- hmac16 = HMAC-SHA256(org_secret, payload) 十六进制摘要前 16 字符；
- 校验顺序：格式 → 签名（常数时间）→ 时效 → 用次 → 吊销（用次/吊销在
  service 层查表，本模块只做纯函数部分，便于单测）。

本模块不抛 HTTP 异常：校验失败返回带 reason 的结果，由路由层映射
协议错误码（403/410 等）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time as _time
from dataclasses import dataclass
from typing import Optional, Tuple

CODE_PREFIX = "DDWORG-"
SIG_LEN = 16  # hmac16：hex 摘要前 16 字符


@dataclass
class BindCodePayload:
    org_id: str
    exp_ts: int
    nonce: str


@dataclass
class VerifyResult:
    ok: bool
    reason: Optional[str] = None  # malformed / bad_signature / expired
    payload: Optional[BindCodePayload] = None


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sig16(secret: str, payload: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()[:SIG_LEN]


def _parse(code: str) -> Optional[Tuple[str, BindCodePayload, str]]:
    """拆出 (payload 明文, 结构化字段, sig16)；格式不合法返回 None。"""
    text = (code or "").strip()
    if not text.startswith(CODE_PREFIX):
        return None
    b64, dot, sig = text[len(CODE_PREFIX):].partition(".")
    if not dot or not sig:
        return None
    try:
        payload = _b64url_decode(b64).decode("utf-8")
        parts = payload.split("|")
        if len(parts) != 3:
            return None
        org_id, exp_str, nonce = parts
        exp_ts = int(exp_str)
        if not org_id or len(nonce) < 8:
            return None
    except (ValueError, UnicodeDecodeError):
        return None
    return payload, BindCodePayload(org_id=org_id, exp_ts=exp_ts, nonce=nonce), sig


def issue_code(org_id: str, org_secret: str, exp_ts: int, nonce: Optional[str] = None) -> str:
    """签发一枚绑定码（nonce ≥8 hex，保证同分钟多次签发互不相同）。"""
    if not org_id or "|" in org_id:
        raise ValueError("org_id must be non-empty and contain no '|'")
    payload = f"{org_id}|{int(exp_ts)}|{nonce or secrets.token_hex(8)}"
    return f"{CODE_PREFIX}{_b64url_encode(payload.encode('utf-8'))}.{_sig16(org_secret, payload)}"


def verify_signature(code: str, org_secret: str, *, now_ts: Optional[int] = None) -> VerifyResult:
    """校验格式 + HMAC（常数时间比较）+ 时效。

    不查用次/吊销记录（服务层职责）；时效在此一并校验是因为 exp_ts
    内嵌在码里，无需查表即可判定。
    """
    parsed = _parse(code)
    if parsed is None:
        return VerifyResult(False, "malformed")
    payload, fields, sig = parsed
    if not hmac.compare_digest(_sig16(org_secret, payload), sig):
        return VerifyResult(False, "bad_signature")
    if now_ts is None:
        now_ts = int(_time.time())
    if fields.exp_ts <= now_ts:
        return VerifyResult(False, "expired", fields)
    return VerifyResult(True, payload=fields)


def extract_org_id(code: str) -> Optional[str]:
    """仅解析 org_id（查组织用）；格式不合法返回 None，不校验签名。"""
    parsed = _parse(code)
    return None if parsed is None else parsed[1].org_id
