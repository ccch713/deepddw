"""幂等迁移脚本：数字员工体系 P0 模型扩展。

执行方式：
  cd /path/to/ddw-ai-hub
  python scripts/migrate_digital_employee_p0.py

幂等性：
  - PRAGMA table_info 检查列是否已存在
  - 已存在的列不重复添加
  - 不 DROP 任何表/列
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "ddw_main.db"

# 列定义：(表名, 列名, SQL类型, 默认值)
COLUMNS_TO_ADD = [
    # org_departments
    ("org_departments", "manager_user_id", "INTEGER", "NULL"),
    # org_digital_agents
    ("org_digital_agents", "job_objective", "TEXT", "''"),
    ("org_digital_agents", "report_to", "INTEGER", "NULL"),
    ("org_digital_agents", "decision_scope", "TEXT", "'[]'"),
    ("org_digital_agents", "work_boundary", "TEXT", "''"),
    # org_agent_skills
    ("org_agent_skills", "proficiency", "VARCHAR(20)", "'junior'"),
    ("org_agent_skills", "trigger_conditions", "TEXT", "'[]'"),
    ("org_agent_skills", "sla_seconds", "INTEGER", "NULL"),
    # flow_definitions
    ("flow_definitions", "input_spec", "TEXT", "NULL"),
    ("flow_definitions", "output_spec", "TEXT", "NULL"),
    ("flow_definitions", "cross_dept_review_config", "TEXT", "NULL"),
    # flow_reviews
    ("flow_reviews", "checklist_results", "TEXT", "'[]'"),
    ("flow_reviews", "skill_merger_approved", "BOOLEAN", "0"),
    ("flow_reviews", "review_deadline", "TIMESTAMP", "NULL"),
    ("flow_reviews", "remind_count", "INTEGER", "0"),
]


def get_existing_columns(conn: sqlite3.Connection, table: str) -> set:
    """获取表的已有列名集合。"""
    try:
        cursor = conn.execute(f"PRAGMA table_info({table})")
        return {row[1] for row in cursor.fetchall()}
    except Exception:
        return set()


def migrate(db_path: Path) -> None:
    if not db_path.exists():
        print(f"❌ 数据库不存在: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    added = 0
    skipped = 0
    errors = []

    for table, column, col_type, default in COLUMNS_TO_ADD:
        existing = get_existing_columns(conn, table)
        if not existing:
            print(f"⚠️  表 {table} 不存在，跳过")
            skipped += 1
            continue
        if column in existing:
            print(f"  ✓ {table}.{column} 已存在，跳过")
            skipped += 1
            continue
        try:
            sql = f"ALTER TABLE {table} ADD COLUMN {column} {col_type} DEFAULT {default}"
            conn.execute(sql)
            print(f"  ✅ {table}.{column} 已添加 ({col_type}, DEFAULT {default})")
            added += 1
        except Exception as e:
            print(f"  ❌ {table}.{column} 添加失败: {e}")
            errors.append(f"{table}.{column}: {e}")

    conn.commit()
    conn.close()

    print(f"\n{'='*50}")
    print(f"迁移完成: 添加 {added} 列, 跳过 {skipped} 列, 错误 {len(errors)} 个")
    if errors:
        print("错误详情:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)


if __name__ == "__main__":
    migrate(DB_PATH)
