"""幂等迁移脚本：数字员工体系 P4 — DigitalAgentTemplate 模板表。

执行方式：
  cd /path/to/ddw-ai-hub
  python scripts/migrate_digital_employee_p4.py

幂等性：
  - CREATE TABLE IF NOT EXISTS
  - CREATE INDEX IF NOT EXISTS
  - 不 DROP 任何表/列
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "ddw_main.db"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS digital_agent_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    template_name VARCHAR(200) NOT NULL,
    template_type VARCHAR(20) NOT NULL DEFAULT 'employee_created',
    created_by INTEGER NOT NULL REFERENCES users(id),
    department_id INTEGER NOT NULL REFERENCES org_departments(id),
    agent_name VARCHAR(100) NOT NULL,
    job_objective TEXT NOT NULL DEFAULT '',
    role VARCHAR(100) NOT NULL,
    decision_scope TEXT DEFAULT '[]',
    work_boundary TEXT NOT NULL DEFAULT '',
    skills TEXT NOT NULL DEFAULT '[]',
    input_spec TEXT,
    output_spec TEXT,
    status VARCHAR(30) NOT NULL DEFAULT 'draft',
    validation_results TEXT,
    approval_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    approved_by INTEGER,
    approved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

INDEX_SQLS = [
    "CREATE INDEX IF NOT EXISTS ix_templates_tenant ON digital_agent_templates(tenant_id);",
    "CREATE INDEX IF NOT EXISTS ix_templates_dept ON digital_agent_templates(department_id);",
    "CREATE INDEX IF NOT EXISTS ix_templates_status ON digital_agent_templates(status);",
]


def migrate(db_path: Path) -> None:
    if not db_path.exists():
        print(f"❌ 数据库不存在: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))

    # 检查表是否已存在
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='digital_agent_templates'"
    )
    if cursor.fetchone():
        print("  ✓ digital_agent_templates 表已存在，跳过")
    else:
        conn.execute(CREATE_TABLE_SQL)
        print("  ✅ digital_agent_templates 表已创建")

    # 创建索引
    for idx_sql in INDEX_SQLS:
        conn.execute(idx_sql)
    print("  ✅ 索引已就绪")

    conn.commit()
    conn.close()
    print("\n迁移完成: P4 digital_agent_templates")


if __name__ == "__main__":
    migrate(DB_PATH)
