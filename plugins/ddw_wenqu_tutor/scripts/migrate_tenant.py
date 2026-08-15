#!/usr/bin/env python3
"""问渠分租户迁移脚本（2026-08-14）。

为 6 张学习表（wenqu_sessions/messages/wrong_answers/progress/
parent_reports/study_events）添加 tenant_id 列，存量数据挂到
默认家庭租户（name='问渠默认家庭'）。题库/教材 3 张共享表不动。

用法:
    python3 plugins/ddw_wenqu_tutor/scripts/migrate_tenant.py \
        --url "sqlite:////opt/ddw/ddw-ai-hub/data/ddw_main.db"
    # PG 示例：
    python3 plugins/ddw_wenqu_tutor/scripts/migrate_tenant.py \
        --url "postgresql+psycopg2://user:pass@host:5432/ddw"
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import create_engine, inspect, text

# 学习数据 6 表（需加 tenant_id）
TENANT_TABLES = [
    "wenqu_sessions",
    "wenqu_messages",
    "wenqu_wrong_answers",
    "wenqu_progress",
    "wenqu_parent_reports",
    "wenqu_study_events",
]
# 题库元数据列（2026-08-14：年份默认/地域/学校/上传者，M1 启用筛选）
QUESTION_META_COLUMNS = [
    ("province", "VARCHAR(32)", "TEXT"),
    ("city", "VARCHAR(32)", "TEXT"),
    ("school", "VARCHAR(64)", "TEXT"),
    ("contributor", "VARCHAR(32)", "TEXT"),
]
DEFAULT_FAMILY_NAME = "问渠默认家庭"


def _dialect(url: str) -> str:
    return url.split(":", 1)[0]


def ensure_default_tenant(conn) -> int:
    """找到或创建默认家庭租户，返回其 id。"""
    row = conn.execute(
        text("SELECT id FROM tenants WHERE name = :n LIMIT 1"),
        {"n": DEFAULT_FAMILY_NAME},
    ).first()
    if row:
        return int(row[0])
    result = conn.execute(
        text(
            "INSERT INTO tenants (name, plan, status, created_at, updated_at) "
            "VALUES (:n, 'free', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
        {"n": DEFAULT_FAMILY_NAME},
    )
    conn.commit()
    return int(result.lastrowid)


def migrate(url: str) -> None:
    engine = create_engine(url)
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())

    if "tenants" not in existing:
        print("❌ 未找到 tenants 表，请先初始化 DDW 底座（core 建表）再迁移。")
        sys.exit(1)

    with engine.connect() as conn:
        tid = ensure_default_tenant(conn)
        print(f"✔ 默认家庭租户 id={tid}")

        for table in TENANT_TABLES:
            if table not in existing:
                print(f"  · {table} 不存在，跳过")
                continue
            cols = {c["name"] for c in inspector.get_columns(table)}
            if "tenant_id" in cols:
                print(f"  · {table} 已有 tenant_id，跳过")
                continue
            if _dialect(url) == "sqlite":
                ddl = (
                    f"ALTER TABLE {table} "
                    f"ADD COLUMN tenant_id INTEGER NOT NULL DEFAULT {tid}"
                )
            else:
                ddl = (
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "
                    f"tenant_id BIGINT NOT NULL DEFAULT {tid} "
                    f"REFERENCES tenants(id)"
                )
            conn.execute(text(ddl))
            conn.commit()
            print(f"✔ {table}.tenant_id 已添加（存量数据挂到租户 {tid}）")

        # 题库元数据列（M1 地域/学校/上传者；年份列模型层已默认当前年）
        if "wenqu_questions" in existing:
            qcols = {c["name"] for c in inspector.get_columns("wenqu_questions")}
            for col, pg_type, sqlite_type in QUESTION_META_COLUMNS:
                if col in qcols:
                    continue
                if _dialect(url) == "sqlite":
                    ddl = f"ALTER TABLE wenqu_questions ADD COLUMN {col} {sqlite_type}"
                else:
                    ddl = (
                        f"ALTER TABLE wenqu_questions ADD COLUMN IF NOT EXISTS "
                        f"{col} {pg_type}"
                    )
                conn.execute(text(ddl))
                conn.commit()
                print(f"✔ wenqu_questions.{col} 已添加（M1 地域/学校筛选预留）")

    print("\n✅ 迁移完成。提示：分租户后 API 请求必须携带 JWT"
          "（TenantContextMiddleware 解析 tid），无 JWT 的请求不做过滤。")


def main() -> None:
    ap = argparse.ArgumentParser(description="问渠分租户迁移")
    ap.add_argument(
        "--url",
        default="sqlite:///data/ddw_main.db",
        help="数据库 URL（默认 sqlite:///data/ddw_main.db）",
    )
    args = ap.parse_args()
    migrate(args.url)


if __name__ == "__main__":
    main()
