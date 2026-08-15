"""DDW KPI Dashboard - 跨插件数据聚合器."""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _find_sibling_db(our_db: Path, name: str) -> Path | None:
    """在 plugins/ 下找兄弟 db."""
    candidates = [
        our_db.parent / f"{name}.db",
        our_db.parent.parent / f"ddw_{name}" / "data" / f"{name}.db",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _safe_query(db_path: Path | None, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    if db_path is None or not db_path.exists():
        return []
    try:
        with sqlite3.connect(db_path, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except sqlite3.Error:
        return []


def overview(our_db: Path, period: str) -> dict[str, Any]:
    """经营总览."""
    # 患者
    patient_db = _find_sibling_db(our_db, "patient_crm")
    patients = _safe_query(patient_db, "SELECT * FROM patients")
    total_patients = len(patients)
    # 简化: 用 created_at 起始
    new_patients = sum(
        1 for p in patients
        if (p.get("created_at") or "").startswith(period)
    )
    # 病历
    emr_db = _find_sibling_db(our_db, "dental_emr")
    records = _safe_query(emr_db, "SELECT treatment_type FROM dental_records")
    total_records = len(records)
    # 收入
    pay_db = _find_sibling_db(our_db, "payment")
    income_rows = _safe_query(
        pay_db,
        "SELECT actual_amount, status FROM payment_records "
        "WHERE substr(created_at,1,7)=? AND status='paid'",
        (period,),
    )
    total_income = sum(float(r["actual_amount"]) for r in income_rows)
    avg_income = total_income / total_patients if total_patients else 0.0
    # 诊疗类型 top
    tt_count: dict[str, int] = defaultdict(int)
    for r in records:
        tt_count[r.get("treatment_type", "unknown")] += 1
    top_treatment = max(tt_count, key=tt_count.get) if tt_count else None
    return {
        "period": period,
        "total_income": round(total_income, 2),
        "total_patients": total_patients,
        "new_patients": new_patients,
        "total_records": total_records,
        "avg_income_per_patient": round(avg_income, 2),
        "top_treatment": top_treatment,
    }


def doctors(our_db: Path, period: str) -> list[dict[str, Any]]:
    """医生 KPI."""
    pay_db = _find_sibling_db(our_db, "payment")
    emr_db = _find_sibling_db(our_db, "dental_emr")
    # 医生收入 + 病历数
    pay_rows = _safe_query(
        pay_db,
        "SELECT doctor_id, actual_amount FROM payment_records "
        "WHERE substr(created_at,1,7)=? AND status='paid'",
        (period,),
    )
    emr_rows = _safe_query(
        emr_db,
        "SELECT doctor_id, patient_id FROM dental_records "
        "WHERE substr(created_at,1,7)=?",
        (period,),
    )
    doc_db = _find_sibling_db(our_db, "doctor_schedule")
    doc_rows = _safe_query(doc_db, "SELECT id, name FROM doctors")
    name_map = {r["id"]: r["name"] for r in doc_rows}
    income_by_doc: dict[str, float] = defaultdict(float)
    for r in pay_rows:
        income_by_doc[r["doctor_id"]] += float(r["actual_amount"])
    patients_by_doc: dict[str, set[str]] = defaultdict(set)
    records_by_doc: dict[str, int] = defaultdict(int)
    for r in emr_rows:
        did = r["doctor_id"]
        patients_by_doc[did].add(r["patient_id"])
        records_by_doc[did] += 1
    out: list[dict[str, Any]] = []
    for did, income in income_by_doc.items():
        out.append({
            "doctor_id": did,
            "name": name_map.get(did, did),
            "patient_count": len(patients_by_doc.get(did, set())),
            "record_count": records_by_doc.get(did, 0),
            "income": round(income, 2),
            "commission": 0.0,
            "satisfaction_avg": None,
        })
    out.sort(key=lambda x: x["income"], reverse=True)
    return out


def treatments(our_db: Path, period: str) -> list[dict[str, Any]]:
    """诊疗类型统计."""
    emr_db = _find_sibling_db(our_db, "dental_emr")
    pay_db = _find_sibling_db(our_db, "payment")
    rows = _safe_query(
        emr_db,
        "SELECT treatment_type, patient_id, doctor_id, id FROM dental_records "
        "WHERE substr(created_at,1,7)=?",
        (period,),
    )
    # 收入按医生聚合（粗略：实际应该按病历 → 收费）
    pay_rows = _safe_query(
        pay_db,
        "SELECT doctor_id, items FROM payment_records "
        "WHERE substr(created_at,1,7)=? AND status='paid'",
        (period,),
    )
    income_by_tt: dict[str, float] = defaultdict(float)
    for r in pay_rows:
        items_raw = r.get("items")
        if not items_raw:
            continue
        try:
            items = json.loads(items_raw)
        except json.JSONDecodeError:
            continue
        for it in items:
            tt = it.get("treatment_type", "general")
            income_by_tt[tt] += float(it.get("subtotal", 0))
    count_by_tt: dict[str, int] = defaultdict(int)
    for r in rows:
        count_by_tt[r["treatment_type"]] += 1
    all_tt = set(count_by_tt) | set(income_by_tt)
    out: list[dict[str, Any]] = []
    for tt in sorted(all_tt):
        out.append({
            "treatment_type": tt,
            "count": count_by_tt.get(tt, 0),
            "income": round(income_by_tt.get(tt, 0.0), 2),
        })
    out.sort(key=lambda x: x["count"], reverse=True)
    return out


def patients(our_db: Path, period: str) -> dict[str, int]:
    """患者来源分布."""
    patient_db = _find_sibling_db(our_db, "patient_crm")
    rows = _safe_query(
        patient_db,
        "SELECT source FROM patients WHERE substr(created_at,1,7)=?",
        (period,),
    )
    out: dict[str, int] = defaultdict(int)
    for r in rows:
        out[r.get("source", "unknown")] += 1
    return dict(out)


def trend(our_db: Path, months: int = 6) -> list[dict[str, Any]]:
    """最近 N 个月趋势."""
    pay_db = _find_sibling_db(our_db, "payment")
    emr_db = _find_sibling_db(our_db, "dental_emr")
    rows = _safe_query(
        pay_db,
        "SELECT actual_amount, substr(created_at,1,7) AS p FROM payment_records WHERE status='paid'",
    )
    rec_rows = _safe_query(
        emr_db,
        "SELECT substr(created_at,1,7) AS p FROM dental_records",
    )
    income_by_month: dict[str, float] = defaultdict(float)
    for r in rows:
        income_by_month[r["p"]] += float(r["actual_amount"])
    records_by_month: dict[str, int] = defaultdict(int)
    for r in rec_rows:
        records_by_month[r["p"]] += 1
    # 取最近 N 个月
    today = datetime.now(timezone.utc)
    keys: list[str] = []
    for i in range(months - 1, -1, -1):
        y = today.year
        m = today.month - i
        while m <= 0:
            m += 12
            y -= 1
        keys.append(f"{y:04d}-{m:02d}")
    return [
        {
            "period": k,
            "income": round(income_by_month.get(k, 0.0), 2),
            "records": records_by_month.get(k, 0),
        }
        for k in keys
    ]
