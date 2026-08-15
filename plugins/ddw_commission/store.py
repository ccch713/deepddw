"""DDW Commission - 存储."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class CommissionStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS commission_rules (
                    id TEXT PRIMARY KEY,
                    treatment_type TEXT NOT NULL,
                    doctor_id TEXT,
                    percentage REAL NOT NULL,
                    min_amount REAL DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS commission_records (
                    id TEXT PRIMARY KEY,
                    doctor_id TEXT NOT NULL,
                    period TEXT NOT NULL,
                    total_income REAL NOT NULL,
                    commission_amount REAL NOT NULL,
                    rule_applied TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    confirmed_at TEXT,
                    breakdown TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_records_period_doctor "
                "ON commission_records(period, doctor_id)"
            )

    def create_rule(self, data: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        rid = data.get("id") or f"rule_{uuid.uuid4().hex[:6]}"
        payload = dict(data)
        payload["id"] = rid
        payload.setdefault("is_active", True)
        payload.setdefault("doctor_id", None)
        payload["created_at"] = now
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO commission_rules (
                    id, treatment_type, doctor_id, percentage,
                    min_amount, is_active, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["id"], payload["treatment_type"],
                    payload["doctor_id"], payload["percentage"],
                    payload["min_amount"], int(payload["is_active"]),
                    payload["created_at"],
                ),
            )
        return self.get_rule(rid) or {}

    def list_rules(self, treatment_type: Optional[str] = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if treatment_type:
                rows = conn.execute(
                    "SELECT * FROM commission_rules WHERE treatment_type=?",
                    (treatment_type,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM commission_rules ORDER BY treatment_type"
                ).fetchall()
        return [dict(r) for r in rows]

    def get_rule(self, rule_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM commission_rules WHERE id=?", (rule_id,)
            ).fetchone()
        return dict(row) if row else None

    def update_rule(self, rule_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
        if not updates:
            return self.get_rule(rule_id)
        if "is_active" in updates:
            updates["is_active"] = int(bool(updates["is_active"]))
        fields = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [rule_id]
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE commission_rules SET {fields} WHERE id=?", tuple(values)
            )
        return self.get_rule(rule_id)

    def create_record(self, data: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        rid = data.get("id") or f"cr_{uuid.uuid4().hex[:8]}"
        payload = dict(data)
        payload["id"] = rid
        payload.setdefault("status", "pending")
        payload.setdefault("confirmed_at", None)
        payload.setdefault("breakdown", [])
        payload["breakdown"] = json.dumps(payload["breakdown"], ensure_ascii=False)
        payload["created_at"] = now
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO commission_records (
                    id, doctor_id, period, total_income, commission_amount,
                    rule_applied, status, confirmed_at, breakdown, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["id"], payload["doctor_id"], payload["period"],
                    payload["total_income"], payload["commission_amount"],
                    payload["rule_applied"], payload["status"],
                    payload["confirmed_at"], payload["breakdown"],
                    payload["created_at"],
                ),
            )
        return self.get_record(rid) or {}

    def get_record(self, record_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM commission_records WHERE id=?", (record_id,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("breakdown"):
            try:
                d["breakdown"] = json.loads(d["breakdown"])
            except json.JSONDecodeError:
                d["breakdown"] = []
        return d

    def list_records(self, period: Optional[str] = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if period:
                rows = conn.execute(
                    "SELECT * FROM commission_records WHERE period=? "
                    "ORDER BY doctor_id",
                    (period,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM commission_records ORDER BY period DESC, doctor_id"
                ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("breakdown"):
                try:
                    d["breakdown"] = json.loads(d["breakdown"])
                except json.JSONDecodeError:
                    d["breakdown"] = []
            out.append(d)
        return out

    def update_record(
        self, record_id: str, updates: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        if not updates:
            return self.get_record(record_id)
        fields = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [record_id]
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE commission_records SET {fields} WHERE id=?", tuple(values)
            )
        return self.get_record(record_id)

    def total_rules(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM commission_rules").fetchone()[0])
