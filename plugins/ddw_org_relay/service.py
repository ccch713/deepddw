"""org_relay 业务层：组织 / 绑定码 / 绑定关系 / 成员令牌 / 用量。

边界（对齐 2026-08-15 开源边界与 bindcode-v1）：
- 只记录「哪些用户（设备侧标识）绑定了本实例」，不建账号/角色体系；
- 成员级 access_token 与实例管理 Token（superadmin）完全隔离，
  仅能调用本插件 chat 端点；
- org_secret 只存 Fernet 密文，仅在创建/轮换响应中露出一次；
- 日志与流水只落元数据。
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from . import bindcode
from . import store

MEMBER_TOKEN_PREFIX = "orgm_"
_ORG_PLANS = ("trial", "light", "ent")

_write_lock = threading.Lock()


class ServiceError(Exception):
    """业务错误：code 为协议 HTTP 状态码，message 面向调用方。"""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> int:
    return int(time.time())


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ #
# 组织管理
# ------------------------------------------------------------------ #

def create_org(name: str, plan: str = "light", *, quota_requests: Optional[int] = None) -> Dict[str, Any]:
    plan = plan if plan in _ORG_PLANS else "light"
    org_id = f"org_{uuid.uuid4().hex[:8]}"
    secret = secrets.token_hex(32)  # ≥32 字节（hex 64 字符），仅此一次返回
    now = _now()
    with _write_lock, store.get_conn() as conn:
        store.insert_org(conn, org_id=org_id, name=name, plan=plan, secret=secret, now_ts=now)
        if quota_requests is not None:
            conn.execute(
                "UPDATE orgs SET quota_requests=? WHERE org_id=?", (quota_requests, org_id))
        store.log_usage(conn, org_id=org_id, user_id=None, kind="org_created", now_ts=now)
    return {"org_id": org_id, "name": name, "plan": plan, "org_secret": secret,
            "quota_requests": quota_requests}


def get_org(conn: sqlite3.Connection, org_id: str, *, active_only: bool = True) -> Optional[sqlite3.Row]:
    sql = "SELECT * FROM orgs WHERE org_id=?"
    if active_only:
        sql += " AND status='active'"
    return conn.execute(sql, (org_id,)).fetchone()


def list_orgs(limit: int = 100) -> List[Dict[str, Any]]:
    with store.get_conn() as conn:
        rows = conn.execute(
            "SELECT o.*, (SELECT COUNT(*) FROM org_bindings b WHERE b.org_id=o.org_id "
            "  AND b.unbound_at IS NULL AND b.revoked=0) AS active_members "
            "FROM orgs o ORDER BY o.created_at DESC LIMIT ?",
            (min(max(limit, 1), 500),),
        ).fetchall()
    return [dict(store.row_to_org(r), active_members=r["active_members"]) for r in rows]


def org_detail(org_id: str) -> Dict[str, Any]:
    with store.get_conn() as conn:
        org = get_org(conn, org_id, active_only=False)
        if org is None:
            raise ServiceError(404, "org not found")
        members = conn.execute(
            "SELECT user_id, bound_at, unbound_at, revoked FROM org_bindings "
            "WHERE org_id=? ORDER BY id DESC LIMIT 200",
            (org_id,),
        ).fetchall()
        codes = conn.execute(
            "SELECT code, exp_ts, max_uses, used_count, revoked, created_at FROM org_codes "
            "WHERE org_id=? ORDER BY created_at DESC LIMIT 50",
            (org_id,),
        ).fetchall()
        usage = _usage_summary(conn, org_id)
    return {
        "org": store.row_to_org(org),
        "members": [dict(m) for m in members],
        "bind_codes": [dict(c) for c in codes],
        "usage": usage,
    }


def set_org_status(org_id: str, status: str) -> Dict[str, Any]:
    if status not in ("active", "disabled"):
        raise ServiceError(400, "status must be active|disabled")
    with _write_lock, store.get_conn() as conn:
        cur = conn.execute("UPDATE orgs SET status=? WHERE org_id=?", (status, org_id))
        if cur.rowcount == 0:
            raise ServiceError(404, "org not found")
    return {"org_id": org_id, "status": status}


def set_org_quota(org_id: str, quota_requests: Optional[int]) -> Dict[str, Any]:
    if quota_requests is not None and quota_requests < 0:
        raise ServiceError(400, "quota_requests must be >= 0 or null")
    with _write_lock, store.get_conn() as conn:
        cur = conn.execute("UPDATE orgs SET quota_requests=? WHERE org_id=?",
                           (quota_requests, org_id))
        if cur.rowcount == 0:
            raise ServiceError(404, "org not found")
    return {"org_id": org_id, "quota_requests": quota_requests}


def rotate_secret(org_id: str) -> Dict[str, Any]:
    new_secret = secrets.token_hex(32)
    now = _now()
    with _write_lock, store.get_conn() as conn:
        if get_org(conn, org_id, active_only=False) is None:
            raise ServiceError(404, "org not found")
        store.rotate_org_secret(conn, org_id=org_id, new_secret=new_secret, now_ts=now)
        store.log_usage(conn, org_id=org_id, user_id=None, kind="secret_rotated", now_ts=now)
    # 轮换后旧码在时效内仍有效（bindcode-v1 §6，prev_secret 兜底验签）
    return {"org_id": org_id, "org_secret": new_secret, "note": "old codes stay valid until expiry"}


# ------------------------------------------------------------------ #
# 绑定码
# ------------------------------------------------------------------ #

def issue_bindcodes(
    org_id: str,
    *,
    ttl_min: int = 15,
    max_uses: int = 50,
    count: int = 1,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    ttl_min = min(max(ttl_min, 1), 1440)
    max_uses = min(max(max_uses, 1), 1000)
    count = min(max(count, 1), 50)
    now = _now()
    codes: List[str] = []
    with _write_lock, store.get_conn() as conn:
        org = get_org(conn, org_id)
        if org is None:
            raise ServiceError(404, "org not found")
        secret = store.row_to_org(org, with_secret=True)["secret"]
        for _ in range(count):
            exp_ts = now + ttl_min * 60
            code = bindcode.issue_code(org_id, secret, exp_ts)
            conn.execute(
                "INSERT INTO org_codes(code, org_id, exp_ts, max_uses, note, created_at) "
                "VALUES(?,?,?,?,?,?)",
                (code, org_id, exp_ts, max_uses, note, now),
            )
            codes.append(code)
    return {"codes": codes, "org_id": org_id, "ttl_min": ttl_min, "max_uses": max_uses}


def revoke_bindcodes(org_id: str, *, code: Optional[str] = None) -> Dict[str, Any]:
    """吊销绑定码：删除记录语义（立即失效，验码返回 404）。"""
    with _write_lock, store.get_conn() as conn:
        if get_org(conn, org_id, active_only=False) is None:
            raise ServiceError(404, "org not found")
        if code:
            cur = conn.execute(
                "DELETE FROM org_codes WHERE org_id=? AND code=?", (org_id, code))
        else:
            cur = conn.execute("DELETE FROM org_codes WHERE org_id=?", (org_id,))
    return {"org_id": org_id, "revoked": cur.rowcount}


def _verify_and_consume_code(conn: sqlite3.Connection, code: str, *, now_ts: int) -> sqlite3.Row:
    """协议 §2.2 全链校验：格式→签名（含轮换兜底）→吊销→时效→用次（通过即计数）。"""
    parsed = bindcode.extract_org_id(code)
    if parsed is None:
        raise ServiceError(403, "invalid bind code")
    org = get_org(conn, parsed)
    if org is None:
        raise ServiceError(403, "invalid bind code")
    with_secret = store.row_to_org(org, with_secret=True)

    result = bindcode.verify_signature(code, with_secret["secret"], now_ts=now_ts)
    if not result.ok and result.reason == "bad_signature" and with_secret.get("prev_secret"):
        # 密钥轮换兜底（§6）：轮换前签发的旧码在时效内仍有效 → prev_secret 复验
        result = bindcode.verify_signature(code, with_secret["prev_secret"], now_ts=now_ts)
    if not result.ok:
        if result.reason == "expired":
            raise ServiceError(410, "bind code expired")
        raise ServiceError(403, "invalid bind code")

    row = conn.execute("SELECT * FROM org_codes WHERE code=?", (code.strip(),)).fetchone()
    if row is None:
        raise ServiceError(404, "bind code revoked")  # 吊销=删记录语义
    if row["exp_ts"] <= now_ts:
        raise ServiceError(410, "bind code expired")
    if row["used_count"] >= row["max_uses"]:
        raise ServiceError(409, "bind code usage exhausted")
    conn.execute("UPDATE org_codes SET used_count=used_count+1 WHERE code=?", (code.strip(),))
    return org


# ------------------------------------------------------------------ #
# 绑定关系
# ------------------------------------------------------------------ #

def active_binding(conn: sqlite3.Connection, user_id: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT b.*, o.name AS org_name, o.plan AS org_plan, o.status AS org_status, "
        "o.quota_requests AS org_quota "
        "FROM org_bindings b JOIN orgs o ON o.org_id=b.org_id "
        "WHERE b.user_id=? AND b.unbound_at IS NULL AND b.revoked=0 AND o.status='active' "
        "ORDER BY b.id DESC LIMIT 1",
        (user_id,),
    ).fetchone()


def do_bind(user_id: str, code: str) -> Dict[str, Any]:
    """绑定：校验码 → 建关系 → 发成员令牌。同组织幂等，异组织 409。"""
    user_id = (user_id or "").strip()
    if not user_id or len(user_id) > 128:
        raise ServiceError(400, "invalid user_id")
    now = _now()
    token = MEMBER_TOKEN_PREFIX + secrets.token_urlsafe(32)
    with _write_lock, store.get_conn() as conn:
        current = active_binding(conn, user_id)
        if current is not None:
            if current["org_id"] == bindcode.extract_org_id(code):
                return org_payload(conn, current)  # 同组织重复绑定：幂等返回，不烧码
            raise ServiceError(409, "already bound to another org, unbind first")
        org = _verify_and_consume_code(conn, code, now_ts=now)
        store.insert_binding(
            conn, org_id=org["org_id"], user_id=user_id,
            token=token, token_hash=_token_hash(token), now_ts=now,
        )
        store.log_usage(conn, org_id=org["org_id"], user_id=user_id, kind="bind", now_ts=now)
        row = active_binding(conn, user_id)
        assert row is not None
        return org_payload(conn, row)


def do_unbind(user_id: str, *, by: str = "user") -> Dict[str, Any]:
    """解绑（幂等）：成员令牌随之失效；本侧不持有也不删除用户个人数据。"""
    user_id = (user_id or "").strip()
    now = _now()
    with _write_lock, store.get_conn() as conn:
        row = active_binding(conn, user_id)
        if row is not None:
            conn.execute(
                "UPDATE org_bindings SET unbound_at=? WHERE id=? AND unbound_at IS NULL",
                (now, row["id"]),
            )
            store.log_usage(conn, org_id=row["org_id"], user_id=user_id,
                            kind=f"unbind:{by}", now_ts=now)
    return {"bound": False}


def org_state(user_id: str) -> Dict[str, Any]:
    user_id = (user_id or "").strip()
    with store.get_conn() as conn:
        row = active_binding(conn, user_id)
        if row is None:
            return {"bound": False, "org": None, "org_consumed_total": 0}
        payload = org_payload(conn, row)
        payload["org_consumed_total"] = _usage_summary(conn, row["org_id"])["requests_ok"]
        return payload


def org_payload(conn: sqlite3.Connection, binding: sqlite3.Row) -> Dict[str, Any]:
    """协议 §3.1 响应体：org 必选字段 + v1 可选扩展（server_base_url/access_token/models）。"""
    from .router import resolve_server_base_url  # 延迟导入避免环

    org = {
        "org_id": binding["org_id"],
        "name": binding["org_name"],
        "plan": binding["org_plan"],
        "bound_at": binding["bound_at"],
        "server_base_url": resolve_server_base_url(),
        "access_token": store.binding_token(binding),
    }
    models = available_models()
    if models:
        org["models"] = models
    return {"bound": True, "org": org}


# ------------------------------------------------------------------ #
# 成员令牌（chat 端点鉴权）
# ------------------------------------------------------------------ #

def binding_for_token(token: str) -> sqlite3.Row:
    row = store.get_conn().execute(
        "SELECT b.*, o.name AS org_name, o.plan AS org_plan, o.status AS org_status, "
        "o.quota_requests AS org_quota "
        "FROM org_bindings b JOIN orgs o ON o.org_id=b.org_id "
        "WHERE b.token_hash=? AND b.unbound_at IS NULL AND b.revoked=0 AND o.status='active'",
        (_token_hash(token),),
    ).fetchone()
    return row


def check_and_count_quota(org_id: str, quota_requests: Optional[int]) -> None:
    """组织级请求数配额（§3.4 组织额度策略可配置；NULL=不限）。"""
    if quota_requests is None:
        return
    with store.get_conn() as conn:
        used = conn.execute(
            "SELECT COUNT(*) FROM org_usage WHERE org_id=? AND kind='chat'", (org_id,)
        ).fetchone()[0]
    if used >= quota_requests:
        raise ServiceError(429, "org quota exhausted")


def record_chat_usage(
    org_id: str, user_id: str, *, model: Optional[str],
    tokens_in: int, tokens_out: int, ok: bool,
) -> None:
    with _write_lock, store.get_conn() as conn:
        store.log_usage(
            conn, org_id=org_id, user_id=user_id, kind="chat", model=model,
            tokens_in=tokens_in, tokens_out=tokens_out, ok=ok, now_ts=_now(),
        )


def _usage_summary(conn: sqlite3.Connection, org_id: str) -> Dict[str, int]:
    row = conn.execute(
        "SELECT COUNT(*) AS total, SUM(ok) AS ok_cnt, "
        "COALESCE(SUM(tokens_in),0) AS tin, COALESCE(SUM(tokens_out),0) AS tout "
        "FROM org_usage WHERE org_id=? AND kind='chat'",
        (org_id,),
    ).fetchone()
    return {
        "requests_total": row["total"] or 0,
        "requests_ok": int(row["ok_cnt"] or 0),
        "tokens_in": row["tin"],
        "tokens_out": row["tout"],
    }


def usage_report(org_id: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    """管理端对账视图（§3.4 流水按组织聚合；仅元数据）。"""
    with store.get_conn() as conn:
        if org_id:
            orgs = [org_id] if get_org(conn, org_id, active_only=False) else []
            if not orgs:
                raise ServiceError(404, "org not found")
        else:
            orgs = [r["org_id"] for r in
                    conn.execute("SELECT org_id FROM orgs ORDER BY created_at DESC LIMIT 100")]
        items = []
        for oid in orgs:
            summary = _usage_summary(conn, oid)
            top = conn.execute(
                "SELECT user_id, COUNT(*) AS requests, SUM(tokens_in+tokens_out) AS tokens "
                "FROM org_usage WHERE org_id=? AND kind='chat' GROUP BY user_id "
                "ORDER BY requests DESC LIMIT ?",
                (oid, min(max(limit, 1), 200)),
            ).fetchall()
            items.append({"org_id": oid, "usage": summary,
                          "top_users": [dict(t) for t in top]})
    return {"items": items, "total": len(items)}


def available_models() -> List[str]:
    """部署者自配供应商的可用模型（llm_gateway 各 provider 的 default_model）。

    与任何官方渠道无关；网关未就绪/未配置时返回空列表（App 容忍缺省）。
    """
    try:
        from core.llm_gateway.gateway import get_router

        providers = getattr(get_router(), "_providers", {}) or {}
        return sorted({p.default_model for p in providers.values() if getattr(p, "default_model", None)})
    except Exception:  # noqa: BLE001
        return []


def admin_unbind(user_id: str) -> Dict[str, Any]:
    return do_unbind(user_id, by="admin")


def revoke_member(user_id: str) -> Dict[str, Any]:
    """吊销成员令牌（等同解绑，语义留痕 kind=unbind:revoke）。"""
    user_id = (user_id or "").strip()
    now = _now()
    with _write_lock, store.get_conn() as conn:
        row = active_binding(conn, user_id)
        if row is not None:
            conn.execute(
                "UPDATE org_bindings SET unbound_at=?, revoked=1 WHERE id=?",
                (now, row["id"]),
            )
            store.log_usage(conn, org_id=row["org_id"], user_id=user_id,
                            kind="unbind:revoke", now_ts=now)
    return {"bound": False}
