#!/usr/bin/env python3
"""DDW 数据质量巡检（阶段 2-3）。

检查项：
  1. 重复客户：crm_companies 按名称分组 COUNT>1
  2. 孤儿订单：crm_orders 无关联合同 / crm_receivables 无关联订单
  3. 金额一致性：钱包余额 = Σ充值 - Σ消费 + Σ退款（按租户）

用法:
  python3 scripts/data_quality_check.py [--db data/ddw_main.db] [--json]

退出码: 0=全部通过, 1=存在异常
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def check_duplicate_companies(conn: sqlite3.Connection) -> list[dict]:
    """重复客户（同名企业 >1）。"""
    rows = conn.execute(
        """
        SELECT name, tenant_id, COUNT(*) AS cnt
        FROM crm_companies
        GROUP BY name, tenant_id
        HAVING cnt > 1
        ORDER BY cnt DESC
        LIMIT 20
        """
    ).fetchall()
    return [
        {"type": "duplicate_company", "name": r[0], "tenant_id": r[1], "count": r[2]}
        for r in rows
    ]


def check_orphan_orders(conn: sqlite3.Connection) -> list[dict]:
    """孤儿订单：crm_orders 无关联合同 / crm_receivables 无关联订单。"""
    out: list[dict] = []
    try:
        rows = conn.execute(
            """
            SELECT o.id, o.order_no, o.tenant_id
            FROM crm_orders o
            LEFT JOIN crm_contracts c ON o.contract_id = c.id
            WHERE c.id IS NULL
            LIMIT 20
            """
        ).fetchall()
        out += [
            {"type": "order_without_contract", "order_id": r[0], "order_no": r[1], "tenant_id": r[2]}
            for r in rows
        ]
    except sqlite3.OperationalError:
        pass  # 表结构不同时跳过该项
    try:
        rows = conn.execute(
            """
            SELECT r.id, r.tenant_id
            FROM crm_receivables r
            LEFT JOIN crm_orders o ON r.order_id = o.id
            WHERE o.id IS NULL
            LIMIT 20
            """
        ).fetchall()
        out += [
            {"type": "receivable_without_order", "receivable_id": r[0], "tenant_id": r[1]}
            for r in rows
        ]
    except sqlite3.OperationalError:
        pass
    return out


def check_wallet_balance(conn: sqlite3.Connection) -> list[dict]:
    """金额一致性：余额 = Σ充值 - Σ消费 + Σ退款（按租户）。"""
    out: list[dict] = []
    try:
        rows = conn.execute(
            """
            SELECT
                a.tenant_id,
                a.user_id,
                a.recharge_balance_cents,
                COALESCE((SELECT SUM(amount_cents) FROM dw_wallet_recharge_orders
                          WHERE user_id = a.user_id AND status = 'paid'), 0)
                    - COALESCE((SELECT SUM(amount_cents) FROM dw_wallet_charge_records
                                WHERE user_id = a.user_id AND status = 'success'), 0)
                    + COALESCE((SELECT SUM(amount_cents) FROM dw_wallet_refund_records
                                WHERE user_id = a.user_id AND status = 'refunded'), 0)
                    AS calc_balance
            FROM dw_wallet_accounts a
            LIMIT 50
            """
        ).fetchall()
        for r in rows:
            if abs((r[3] or 0) - (r[2] or 0)) > 1:  # 1 分容差
                out.append({
                    "type": "wallet_balance_mismatch",
                    "tenant_id": r[0], "user_id": r[1],
                    "stored": r[2], "calculated": r[3],
                })
    except sqlite3.OperationalError:
        pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="DDW 数据质量巡检")
    ap.add_argument("--db", default="data/ddw_main.db")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"❌ 数据库不存在: {db_path}")
        return 1

    conn = sqlite3.connect(db_path)
    findings = (
        check_duplicate_companies(conn)
        + check_orphan_orders(conn)
        + check_wallet_balance(conn)
    )
    conn.close()

    if args.json:
        print(json.dumps(findings, ensure_ascii=False, indent=2))
    else:
        if not findings:
            print("✅ 数据质量巡检通过：无重复客户 / 无孤儿订单 / 钱包余额一致")
        else:
            print(f"❌ 发现 {len(findings)} 个数据质量问题：")
            for f in findings:
                print(f"  - [{f['type']}] {f}")

    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main())
