"""org_relay 存储（Pattern A：同步 sqlite3 + 幂等建表，同 core/api/teams.py）。

独立库文件 ``data/org_relay.db``（跟随主库 data 目录），便于插件级备份与
停用清理。org_secret / access_token 用 Fernet 加密落盘（复用
core.security.key_store 主密钥），明文只在内存与响应中短暂存在。
"""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from core.security.key_store import decrypt_secret, encrypt_secret

_SCHEMA = """
CREATE TABLE IF NOT EXISTS orgs(
  org_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  plan TEXT NOT NULL DEFAULT 'light',
  secret_enc TEXT NOT NULL,
  prev_secret_enc TEXT,
  secret_rotated_at INTEGER,
  quota_requests INTEGER,
  status TEXT NOT NULL DEFAULT 'active',
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS org_codes(
  code TEXT PRIMARY KEY,
  org_id TEXT NOT NULL,
  exp_ts INTEGER NOT NULL,
  max_uses INTEGER NOT NULL DEFAULT 50,
  used_count INTEGER NOT NULL DEFAULT 0,
  revoked INTEGER NOT NULL DEFAULT 0,
  note TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_org_codes_org ON org_codes(org_id, revoked);
CREATE TABLE IF NOT EXISTS org_bindings(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  org_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  token_enc TEXT NOT NULL,
  bound_at INTEGER NOT NULL,
  unbound_at INTEGER,
  revoked INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_bindings_user ON org_bindings(user_id, unbound_at, revoked);
CREATE INDEX IF NOT EXISTS idx_bindings_org ON org_bindings(org_id, unbound_at, revoked);
CREATE TABLE IF NOT EXISTS org_usage(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  org_id TEXT NOT NULL,
  user_id TEXT,
  kind TEXT NOT NULL,
  model TEXT,
  tokens_in INTEGER NOT NULL DEFAULT 0,
  tokens_out INTEGER NOT NULL DEFAULT 0,
  ok INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_org ON org_usage(org_id, kind, created_at);
"""

_lock = threading.Lock()


def _default_db_path() -> Path:
    """data 目录取自主库路径设置（与 core/api/teams.py 一致），文件名独立。"""
    try:
        from core.config import get_settings

        cfg = get_settings().databases.get("main", {})
        if cfg.get("engine") == "sqlite":
            main_path = Path(cfg.get("path", "./data/ddw_main.db"))
        else:
            main_path = Path("./data/ddw_main.db")
        data_dir = main_path.parent
    except Exception:  # noqa: BLE001 — 独立运行（测试）时兜底
        data_dir = Path("data")
    return data_dir / "org_relay.db"


def db_path() -> Path:
    env = os.environ.get("DDW_ORG_RELAY_DB", "").strip()
    return Path(env) if env else _default_db_path()


def get_conn() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    with _lock:
        conn.executescript(_SCHEMA)
    return conn


# ---- 行 <-> dict 辅助（org_secret 解密只在明确需要处发生）----

def row_to_org(row: sqlite3.Row, *, with_secret: bool = False) -> dict[str, Any]:
    d = {
        "org_id": row["org_id"],
        "name": row["name"],
        "plan": row["plan"],
        "quota_requests": row["quota_requests"],
        "status": row["status"],
        "created_at": row["created_at"],
        "secret_rotated_at": row["secret_rotated_at"],
    }
    if with_secret:
        d["secret"] = decrypt_secret(row["secret_enc"])
        if row["prev_secret_enc"]:
            d["prev_secret"] = decrypt_secret(row["prev_secret_enc"])
    return d


def insert_org(
    conn: sqlite3.Connection, *, org_id: str, name: str, plan: str, secret: str, now_ts: int
) -> None:
    conn.execute(
        "INSERT INTO orgs(org_id, name, plan, secret_enc, created_at) VALUES(?,?,?,?,?)",
        (org_id, name, plan, encrypt_secret(secret), now_ts),
    )


def rotate_org_secret(
    conn: sqlite3.Connection, *, org_id: str, new_secret: str, now_ts: int
) -> None:
    """轮换：旧密钥降级为 prev（时效内的旧码仍可验签，bindcode-v1 §6）。"""
    conn.execute(
        "UPDATE orgs SET prev_secret_enc=secret_enc, secret_enc=?, secret_rotated_at=? "
        "WHERE org_id=?",
        (encrypt_secret(new_secret), now_ts, org_id),
    )


def insert_binding(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    user_id: str,
    token: str,
    token_hash: str,
    now_ts: int,
) -> None:
    conn.execute(
        "INSERT INTO org_bindings(org_id, user_id, token_hash, token_enc, bound_at) "
        "VALUES(?,?,?,?,?)",
        (org_id, user_id, token_hash, encrypt_secret(token), now_ts),
    )


def binding_token(row: sqlite3.Row) -> str:
    return decrypt_secret(row["token_enc"])


def log_usage(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    user_id: Optional[str],
    kind: str,
    model: Optional[str] = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    ok: bool = True,
    now_ts: int,
) -> None:
    """元数据流水（bindcode-v1 §6：不落请求正文/回复内容）。"""
    conn.execute(
        "INSERT INTO org_usage(org_id, user_id, kind, model, tokens_in, tokens_out, ok, created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (org_id, user_id, kind, model, tokens_in, tokens_out, 1 if ok else 0, now_ts),
    )
