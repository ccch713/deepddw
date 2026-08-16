#!/usr/bin/env python3
"""迁移旧 memory_entries → 新分层记忆表（用户/笔记/日志/反思）。

用法：
    python scripts/migrate_memory.py          # 执行迁移并打印结果
    python scripts/migrate_memory.py --check  # 只统计不写库

旧表保留不删（可回滚）；分类规则见 core.knowledge.migrate_memory_entries。
"""
from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="迁移旧记忆到分层记忆")
    parser.add_argument("--check", action="store_true", help="只统计不写库")
    args = parser.parse_args()

    sys.path.insert(0, ".")
    try:
        from core.knowledge import get_conn, migrate_memory_entries

        if args.check:
            conn = get_conn()
            try:
                total = conn.execute(
                    "SELECT COUNT(*) FROM memory_entries"
                ).fetchone()[0]
                print(f"旧 memory_entries 共 {total} 条（--check 不写库）")
            finally:
                from core.knowledge import close_conn
                close_conn(conn)
            return 0

        result = migrate_memory_entries()
        print("迁移完成：")
        for k, v in result.items():
            print(f"  {k}: {v}")
        if result.get("degraded"):
            print("注意：迁移部分降级 -", result.get("note"), file=sys.stderr)
            return 1
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"迁移失败: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
