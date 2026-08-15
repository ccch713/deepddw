"""DDW Payment - 存储."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class PaymentStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS payment_records (
                    id TEXT PRIMARY KEY,
                    patient_id TEXT NOT NULL,
                    doctor_id TEXT NOT NULL,
                    items TEXT NOT NULL,
                    total_amount REAL NOT NULL,
                    discount_amount REAL DEFAULT 0,
                    actual_amount REAL NOT NULL,
                    payment_method TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    paid_at TEXT,
                    receipt_number TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_payments_patient "
                "ON payment_records(patient_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_payments_date "
                "ON payment_records(created_at)"
            )

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        rid = data.get("id") or f"pay_{uuid.uuid4().hex[:8]}"
        payload = dict(data)
        payload["id"] = rid
        payload.setdefault("status", "pending")
        payload.setdefault("paid_at", None)
        payload.setdefault("receipt_number", None)
        payload.setdefault("notes", None)
        payload.setdefault("discount_amount", 0.0)
        payload["items"] = json.dumps(payload.get("items", []), ensure_ascii=False)
        payload["created_at"] = now
        # 收据号 R{YYYYMMDD}{seq}
        if not payload.get("receipt_number") and payload["status"] == "pending":
            payload["receipt_number"] = self._next_receipt_number(
                now[:10].replace("-", ""))
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO payment_records (
                    id, patient_id, doctor_id, items,
                    total_amount, discount_amount, actual_amount,
                    payment_method, status, paid_at, receipt_number, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(payload[k] for k in [
                    "id", "patient_id", "doctor_id", "items",
                    "total_amount", "discount_amount", "actual_amount",
                    "payment_method", "status", "paid_at", "receipt_number", "notes", "created_at",
                ]),
            )
        return self.get(rid) or {}

    def get(self, record_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM payment_records WHERE id=?", (record_id,)
            ).fetchone()
        return self._to_dict(row) if row else None

    def list_records(
        self,
        date: Optional[str] = None,
        patient_id: Optional[str] = None,
        doctor_id: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        where: list[str] = []
        params: list[Any] = []
        if date:
            where.append("substr(created_at,1,10) = ?")
            params.append(date)
        if patient_id:
            where.append("patient_id = ?")
            params.append(patient_id)
        if doctor_id:
            where.append("doctor_id = ?")
            params.append(doctor_id)
        if status:
            where.append("status = ?")
            params.append(status)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        offset = max(0, (page - 1) * page_size)
        with self._connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM payment_records {where_sql}", tuple(params)
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM payment_records {where_sql} "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                tuple(params + [page_size, offset]),
            ).fetchall()
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "records": [self._to_dict(r) for r in rows],
        }

    def update(self, record_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
        if not updates:
            return self.get(record_id)
        fields = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [record_id]
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE payment_records SET {fields} WHERE id=?", tuple(values)
            )
        return self.get(record_id)

    def daily_summary(self, date: str) -> dict[str, Any]:
        rows = self.list_records(date=date, page=1, page_size=10000)["records"]
        income_by_method: dict[str, float] = {}
        total_income = 0.0
        refund_count = 0
        refund_amount = 0.0
        for r in rows:
            if r["status"] == "paid":
                m = r["payment_method"]
                income_by_method[m] = income_by_method.get(
                    m, 0.0) + float(r["actual_amount"])
                total_income += float(r["actual_amount"])
            elif r["status"] == "refunded":
                refund_count += 1
                refund_amount += float(r["actual_amount"])
        return {
            "date": date,
            "total_income": round(total_income, 2),
            "by_method": {k: round(v, 2) for k, v in income_by_method.items()},
            "transaction_count": len([r for r in rows if r["status"] == "paid"]),
            "refund_count": refund_count,
            "refund_amount": round(refund_amount, 2),
        }

    def total_count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM payment_records").fetchone()[0])

    def _next_receipt_number(self, ymd: str) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM payment_records WHERE receipt_number LIKE ?",
                (f"R{ymd}%",),
            ).fetchone()
        seq = int(row[0]) + 1
        return f"R{ymd}{seq:03d}"

    @staticmethod
    def _to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        items = d.get("items")
        if items:
            try:
                d["items"] = json.loads(items)
            except json.JSONDecodeError:
                d["items"] = []
        else:
            d["items"] = []
        return d
