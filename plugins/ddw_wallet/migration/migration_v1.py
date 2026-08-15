"""dw_wallet 三钱包迁移脚本（dry-run + apply）。

迁移逻辑：
1. WalletAccount 删除 balance_cents 列，新增三钱包字段（recharge/income/skin）
2. 旧 balance_cents 值全部迁移到 recharge_balance_cents
3. 新增 Ledger 表
4. 新增其他 G 项所需表

用法：
    dry-run: python migration_v1.py --dry-run
    apply:   python migration_v1.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 添加项目根目录到 sys.path
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text  # noqa: E402


def get_engine(db_url: str):
    """创建同步引擎。"""
    return create_engine(db_url, echo=False)


def check_table_exists(engine, table_name: str) -> bool:
    """检查表是否存在。"""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
            {"name": table_name},
        )
        return result.first() is not None


def check_column_exists(engine, table_name: str, column_name: str) -> bool:
    """检查列是否存在（SQLite PRAGMA）。"""
    with engine.connect() as conn:
        result = conn.execute(text(f"PRAGMA table_info({table_name})"))
        return any(row[1] == column_name for row in result)


def migrate_wallet_account(engine, dry_run: bool = True):
    """迁移 WalletAccount：balance_cents → 三钱包。"""
    table = "dw_wallet_accounts"
    if not check_table_exists(engine, table):
        print(f"  ℹ️  {table} 不存在，跳过迁移")
        return

    # 检查是否已迁移（有 recharge_balance_cents 列）
    if check_column_exists(engine, table, "recharge_balance_cents"):
        print(f"  ✅ {table} 已迁移（三钱包字段存在），跳过")
        return

    # 检查旧列是否存在
    has_old_balance = check_column_exists(engine, table, "balance_cents")

    print(f"  🔄 迁移 {table}:")
    print("     - 删除 balance_cents 列" if has_old_balance else "     - 无 balance_cents 列")
    print("     - 新增 recharge_balance_cents (default 0)")
    print("     - 新增 income_balance_cents (default 0)")
    print("     - 新增 skin_balance_cents (default 0)")

    if dry_run:
        print("  ⚠️  dry-run 模式，不执行 SQL")
        return

    with engine.begin() as conn:
        # SQLite 不支持 DROP COLUMN，创建新表迁移
        # 1. 创建临时表（三钱包结构）
        conn.execute(text("""
            CREATE TABLE dw_wallet_accounts_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR(64) NOT NULL,
                recharge_balance_cents INTEGER NOT NULL DEFAULT 0,
                income_balance_cents INTEGER NOT NULL DEFAULT 0,
                skin_balance_cents INTEGER NOT NULL DEFAULT 0,
                frozen_cents INTEGER NOT NULL DEFAULT 0,
                status VARCHAR(16) NOT NULL DEFAULT 'active',
                version INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # 2. 迁移数据：旧 balance_cents → recharge_balance_cents
        if has_old_balance:
            conn.execute(text("""
                INSERT INTO dw_wallet_accounts_new
                    (id, user_id, recharge_balance_cents, frozen_cents, status, version, created_at, updated_at)
                SELECT id, user_id, balance_cents, frozen_cents, status, version, created_at, updated_at
                FROM dw_wallet_accounts
            """))
        else:
            conn.execute(text("""
                INSERT INTO dw_wallet_accounts_new
                    (id, user_id, frozen_cents, status, version, created_at, updated_at)
                SELECT id, user_id, frozen_cents, status, version, created_at, updated_at
                FROM dw_wallet_accounts
            """))

        # 3. 删除旧表
        conn.execute(text("DROP TABLE dw_wallet_accounts"))

        # 4. 重命名新表
        conn.execute(text("ALTER TABLE dw_wallet_accounts_new RENAME TO dw_wallet_accounts"))

    print("  ✅ 迁移完成")


def create_ledger_table(engine, dry_run: bool = True):
    """创建 Ledger 流水表。"""
    table = "dw_wallet_ledger"
    if check_table_exists(engine, table):
        print(f"  ✅ {table} 已存在，跳过")
        return

    print(f"  🔄 创建 {table}")
    if dry_run:
        print("  ⚠️  dry-run 模式，不执行 SQL")
        return

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE dw_wallet_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                txn_no VARCHAR(40) NOT NULL UNIQUE,
                user_id VARCHAR(64) NOT NULL,
                direction VARCHAR(4) NOT NULL,
                amount_cents INTEGER NOT NULL,
                balance_type VARCHAR(16) NOT NULL,
                ref_id VARCHAR(64) NOT NULL UNIQUE,
                ref_type VARCHAR(32) NOT NULL,
                balance_after INTEGER NOT NULL,
                reason TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))

    print(f"  ✅ {table} 创建完成")


def print_summary(engine):
    """打印迁移后摘要。"""
    print("\n📊 迁移后摘要:")
    with engine.connect() as conn:
        # 表列表
        result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"))
        tables = [row[0] for row in result if row[0].startswith("dw_wallet_")]
        print(f"  表数量: {len(tables)}")
        for t in tables:
            print(f"    - {t}")

        # 账户数量
        if check_table_exists(engine, "dw_wallet_accounts"):
            result = conn.execute(text("SELECT COUNT(*) FROM dw_wallet_accounts"))
            count = result.scalar()
            print(f"\n  账户数量: {count}")

            if count > 0:
                result = conn.execute(text("""
                    SELECT user_id, recharge_balance_cents, income_balance_cents, skin_balance_cents
                    FROM dw_wallet_accounts LIMIT 5
                """))
                print("  前 5 个账户:")
                for row in result:
                    print(f"    user_id={row[0]}, recharge={row[1]}, income={row[2]}, skin={row[3]}")


def main():
    parser = argparse.ArgumentParser(description="dw_wallet 三钱包迁移")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不执行")
    parser.add_argument("--db-url", default="sqlite:///ddw_wallet.db", help="数据库 URL")
    args = parser.parse_args()

    print("🚀 dw_wallet 三钱包迁移脚本")
    print(f"   模式: {'dry-run' if args.dry_run else 'apply'}")
    print(f"   数据库: {args.db_url}")
    print()

    engine = get_engine(args.db_url)

    print("步骤 1: 迁移 WalletAccount（三钱包）")
    migrate_wallet_account(engine, dry_run=args.dry_run)

    print("\n步骤 2: 创建 Ledger 流水表")
    create_ledger_table(engine, dry_run=args.dry_run)

    if not args.dry_run:
        print_summary(engine)

    print("\n✅ 迁移脚本执行完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
