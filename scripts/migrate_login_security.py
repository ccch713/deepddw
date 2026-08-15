"""DDW 登录安全 P0 数据库迁移（SQLite 幂等）"""
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else "/Users/chenye/ddw-ai-hub/data/ddw_main.db"

def main() -> None:
    conn = sqlite3.connect(DB)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    added = []
    if "device_required" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN device_required BOOLEAN DEFAULT 0")
        added.append("device_required")
    if "device_allowlist" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN device_allowlist JSON")
        added.append("device_allowlist")
    if "password_changed_at" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN password_changed_at DATETIME")
        added.append("password_changed_at")
    # 存量账号（昨天之前创建）：有密码的按创建时间计密码生效（避免全量强制首登改密）
    # 今天新建的交付账号保持 NULL → 首登强制改密（初始密码一次性入场）
    conn.execute(
        "UPDATE users SET password_changed_at = created_at "
        "WHERE password_changed_at IS NULL AND password_hash IS NOT NULL "
        "AND created_at < datetime('now', 'start of day')"
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS login_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone VARCHAR(20),
            ip VARCHAR(45),
            user_agent VARCHAR(255),
            method VARCHAR(20) DEFAULT 'password',
            success BOOLEAN DEFAULT 0,
            fail_reason VARCHAR(100),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ix_audit_phone_time ON login_audit(phone, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_audit_ip_time ON login_audit(ip, created_at)")
    # 邮箱绑定字段（幂等）
    if "email" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN email VARCHAR(255)")
        added.append("email")
    if "email_verified" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT 0")
        added.append("email_verified")
    # 存量不动（email 可空；新用户注册强制）
    conn.commit()
    print(f"MIGRATE_OK added={added} login_audit=ready users_cols={len(cols)}")
    conn.close()

if __name__ == "__main__":
    main()
