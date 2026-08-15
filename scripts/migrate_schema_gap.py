#!/usr/bin/env python3
"""通用 schema 迁移：模型 vs 现有库列差异自动 ALTER TABLE ADD COLUMN。

用法：python scripts/migrate_schema_gap.py [--dry-run] [--db PATH]
覆盖场景：TenantMixin/登录安全/订阅等改造后，存量库缺列（本地开发库 + ECS 生产库）。
跳过：NOT NULL 无默认值的列（SQLite ADD COLUMN 限制）；缺表整体（建表走 create_all）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.types import Boolean, Date, DateTime, Float, Integer, Numeric, String

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TYPE_MAP = {
    Integer: "INTEGER",
    Float: "FLOAT",
    Numeric: "FLOAT",
    String: "VARCHAR",
    Boolean: "INTEGER",
    Date: "DATE",
    DateTime: "DATETIME",
}


def _sqlite_type(col) -> str:
    for cls, name in TYPE_MAP.items():
        if isinstance(col.type, cls):
            if isinstance(col.type, String) and col.type.length:
                return f"{name}({col.type.length})"
            return name
    return "VARCHAR"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--db", default=str(ROOT / "data" / "ddw_main.db"))
    args = ap.parse_args()

    import core.database.models as models  # noqa: F401  触发 metadata 注册
    from core.database.session import Base

    eng = create_engine(f"sqlite:///{args.db}")
    insp = inspect(eng)
    existing = {t for t in insp.get_table_names()}
    missing_total = 0

    for table_name, table in Base.metadata.tables.items():
        if table_name not in existing:
            print(f"⏭️  {table_name}: 整表缺失（由 create_all 负责）")
            continue
        db_cols = {c["name"] for c in insp.get_columns(table_name)}
        for col in table.columns:
            if col.name in db_cols:
                continue
            if not col.nullable and col.default is None and col.server_default is None:
                print(f"⚠️  {table_name}.{col.name}: NOT NULL 无默认值，跳过（需手工迁移）")
                continue
            typ = _sqlite_type(col)
            sql = f'ALTER TABLE "{table_name}" ADD COLUMN "{col.name}" {typ}'
            if not args.dry_run:
                with eng.begin() as conn:
                    conn.execute(text(sql))
            missing_total += 1
            print(f"{'[DRY]' if args.dry_run else '[OK] '} {table_name}.{col.name} {typ}")

    print(f"\n{'预测' if args.dry_run else '完成'}: 补 {missing_total} 列")


if __name__ == "__main__":
    main()
