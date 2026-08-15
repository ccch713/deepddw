"""DDW 超管/客户/经销商账号创建（SQLite 直插，幂等）。

用法:
  DDW_PWD_SUPER1=xxx DDW_PWD_SUPER2=xxx python create_ddw_accounts.py <db_path> all
  DDW_PWD_SUPER2=xxx python create_ddw_accounts.py <db_path> superadmin   # 16G: 仅超管
"""
import bcrypt
import hashlib
import json
import os
import sqlite3
import sys
from typing import Dict, Optional

ALLOWLIST = {
    "32G-Mac-mini": {"serial": "D9CXVC9Q5L", "screen_hints": ["2560x1440", "1920x1080"]},
    "128G-MBP": {"serial": "C7M6MG97JL", "screen_hints": ["3456x2234", "2560x1600", "1728x1117"]},
}


def hash_password(pwd: str) -> str:
    pre = hashlib.sha256(pwd.encode("utf-8")).hexdigest().encode("utf-8")
    return bcrypt.hashpw(pre, bcrypt.gensalt(rounds=12)).decode("utf-8")


def get_or_create_tenant(conn: sqlite3.Connection, name: str, plan: str, contact_phone: str) -> int:
    row = conn.execute("SELECT id FROM tenants WHERE name=? LIMIT 1", (name,)).fetchone()
    if row:
        return int(row[0])
    cur = conn.execute(
        "INSERT INTO tenants (name, plan, status, contact_phone) VALUES (?,?,?,?)",
        (name, plan, "active", contact_phone),
    )
    assert cur.lastrowid is not None
    return int(cur.lastrowid)


def upsert_user(conn: sqlite3.Connection, tenant_id: int, phone: str, name: str, role: str,
                password: Optional[str], device_required: bool, allowlist: Optional[dict]) -> str:
    row = conn.execute("SELECT id FROM users WHERE phone=?", (phone,)).fetchone()
    if row:
        conn.execute(
            "UPDATE users SET name=?, role=?, device_required=?, device_allowlist=?, status='active' WHERE id=?",
            (name, role, 1 if device_required else 0,
             json.dumps(allowlist, ensure_ascii=False) if allowlist else None, row[0]),
        )
        return f"updated(id={row[0]})"
    ph = hash_password(password) if password else None
    cur = conn.execute(
        "INSERT INTO users (tenant_id, phone, password_hash, name, role, status, device_required, device_allowlist) "
        "VALUES (?,?,?,?,?, 'active', ?, ?)",
        (tenant_id, phone, ph, name, role, 1 if device_required else 0,
         json.dumps(allowlist, ensure_ascii=False) if allowlist else None),
    )
    assert cur.lastrowid is not None
    return f"created(id={cur.lastrowid})"


def main() -> None:
    db, mode = sys.argv[1], sys.argv[2]
    conn = sqlite3.connect(db)
    print(f"DB={db} mode={mode}")
    results = []

    if mode in ("all", "superadmin"):
        # 锐果运营租户 + 双超管（设备绑定红线）
        t = get_or_create_tenant(conn, "锐果互动", "enterprise", "13367266625")
        p1 = os.environ.get("DDW_PWD_SUPER1", "")
        p2 = os.environ.get("DDW_PWD_SUPER2", "")
        if not p1 or not p2:
            print("ERROR: DDW_PWD_SUPER1/DDW_PWD_SUPER2 required"); sys.exit(1)
        results.append(("13367266625", upsert_user(conn, t, "13367266625", "超级管理员", "owner", p1, True, ALLOWLIST)))
        results.append(("15990720096", upsert_user(conn, t, "15990720096", "超级管理员", "owner", p2, True, ALLOWLIST)))

    if mode == "all":
        # 嘉必优租户 + CIO 万永刚
        t2 = get_or_create_tenant(conn, "嘉必优生物技术(武汉)股份有限公司", "free", "18571998165")
        p3 = os.environ.get("DDW_PWD_JIABIYOU", "")
        if not p3:
            print("ERROR: DDW_PWD_JIABIYOU required"); sys.exit(1)
        results.append(("18571998165", upsert_user(conn, t2, "18571998165", "万永刚", "owner", p3, False, None)))
        # 经销商租户 + 江昆鹏（嘉必优报备）
        t3 = get_or_create_tenant(conn, "经销商-江昆鹏", "free", "13797078252")
        p4 = os.environ.get("DDW_PWD_RESELLER", "")
        if not p4:
            print("ERROR: DDW_PWD_RESELLER required"); sys.exit(1)
        results.append(("13797078252", upsert_user(conn, t3, "13797078252", "江昆鹏(经销商)", "owner", p4, False, None)))

    conn.commit()
    for phone, r in results:
        print(f"  {phone}: {r}")
    print("DONE")
    conn.close()


if __name__ == "__main__":
    main()
