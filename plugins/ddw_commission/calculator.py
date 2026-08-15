"""DDW Commission - 提成计算核心.

跨插件读 ddw_offline_pos 的 paid 记录，按规则分账。
"""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any


def _find_payment_db(commission_db: Path) -> Path | None:
    candidates = [
        commission_db.parent / "offline_pos.db",
        commission_db.parent.parent / "ddw_offline_pos" / "data" / "offline_pos.db",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def aggregate_paid_income_by_doctor(payment_db: Path, period: str) -> dict[str, dict[str, Any]]:
    """读取某月已支付记录，按 (doctor_id, treatment_type) 汇总金额.

    Returns
    -------
    {
      "doc_001": {
        "extraction": 1500.0,
        "implant": 5000.0,
        "total": 6500.0,
      },
      ...
    }
    """
    out: dict[str, dict[str, Any]] = defaultdict(lambda: {"total": 0.0})
    try:
        with sqlite3.connect(payment_db, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT doctor_id, items, substr(created_at,1,7) AS p
                FROM offline_pos_records
                WHERE status='paid' AND substr(created_at,1,7)=?
                """,
                (period,),
            ).fetchall()
    except sqlite3.Error:
        return out
    for r in rows:
        items_raw = r["items"]
        items = []
        if items_raw:
            try:
                items = json.loads(items_raw)
            except json.JSONDecodeError:
                continue
        for it in items:
            tt = it.get("treatment_type", "general")
            amount = float(it.get("subtotal", 0))
            if amount <= 0:
                continue
            doctor = r["doctor_id"]
            bucket = out[doctor]
            bucket[tt] = bucket.get(tt, 0.0) + amount
            bucket["total"] += amount
    return dict(out)


def calculate_for_period(
    commission_db: Path,
    period: str,
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """为指定月份计算所有医生的提成."""
    pay_db = _find_payment_db(commission_db)
    if pay_db is None:
        return []
    income = aggregate_paid_income_by_doctor(pay_db, period)
    out: list[dict[str, Any]] = []
    for doctor, bucket in income.items():
        breakdown: list[dict[str, Any]] = []
        total_commission = 0.0
        # 规则匹配：优先 specific doctor + specific type，然后 specific type then general
        for tt, amount in bucket.items():
            if tt == "total":
                continue
            rule = _match_rule(rules, doctor, tt)
            if rule is None:
                continue
            commission = amount * rule["percentage"]
            if commission < rule.get("min_amount", 0):
                commission = rule["min_amount"]
            breakdown.append({
                "treatment_type": tt,
                "income": round(amount, 2),
                "percentage": rule["percentage"],
                "commission": round(commission, 2),
                "rule_id": rule["id"],
            })
            total_commission += commission
        out.append({
            "doctor_id": doctor,
            "period": period,
            "total_income": round(bucket["total"], 2),
            "commission_amount": round(total_commission, 2),
            "breakdown": breakdown,
        })
    return out


def _match_rule(
    rules: list[dict[str, Any]], doctor_id: str, treatment_type: str
) -> dict[str, Any] | None:
    """优先级: 1) doctor+type  2) type  3) general  4) general+doctor  5) None."""
    priority = [
        ("doctor_id", "treatment_type", lambda r: r.get("doctor_id") == doctor_id and r["treatment_type"] == treatment_type),
        ("type", "treatment_type", lambda r: r["treatment_type"] == treatment_type and not r.get("doctor_id")),
        ("general_doctor", "treatment_type", lambda r: r["treatment_type"] == "general" and r.get("doctor_id") == doctor_id),
        ("general", "treatment_type", lambda r: r["treatment_type"] == "general" and not r.get("doctor_id")),
    ]
    for _, _, pred in priority:
        for r in rules:
            if r.get("is_active", 1) and pred(r):
                return r
    return None
