"""DDW Dental Sterilization - 存储."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


class SterilizationStore:
    EXPIRY_ALERT_DAYS = 7

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
                CREATE TABLE IF NOT EXISTS sterilizers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    model TEXT,
                    location TEXT,
                    last_calibration TEXT,
                    is_active INTEGER DEFAULT 1
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sterilization_batches (
                    id TEXT PRIMARY KEY,
                    batch_number TEXT NOT NULL UNIQUE,
                    instruments TEXT,
                    sterilizer_id TEXT NOT NULL,
                    cycle_type TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    temperature REAL,
                    pressure REAL,
                    indicator_result TEXT DEFAULT 'pass',
                    operator TEXT NOT NULL,
                    expiry_date TEXT NOT NULL,
                    used_by_record_id TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_batches_sterilizer "
                "ON sterilization_batches(sterilizer_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_batches_expiry "
                "ON sterilization_batches(expiry_date)"
            )

    # --- sterilizers ---

    def create_sterilizer(self, data: dict[str, Any]) -> dict[str, Any]:
        sid = data.get("id") or f"ster_{uuid.uuid4().hex[:6]}"
        payload = dict(data)
        payload["id"] = sid
        payload.setdefault("is_active", True)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sterilizers (id, name, model, location, last_calibration, is_active)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["id"], payload["name"], payload.get("model"),
                    payload.get("location"), payload.get("last_calibration"),
                    int(payload["is_active"]),
                ),
            )
        return self.get_sterilizer(sid) or {}

    def get_sterilizer(self, sid: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sterilizers WHERE id=?", (sid,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["is_active"] = bool(d.get("is_active", 1))
        return d

    def list_sterilizers(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM sterilizers ORDER BY name").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["is_active"] = bool(d.get("is_active", 1))
            out.append(d)
        return out

    # --- batches ---

    def create_batch(self, data: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        bid = data.get("id") or f"batch_{uuid.uuid4().hex[:8]}"
        payload = dict(data)
        payload["id"] = bid
        payload.setdefault("indicator_result", "pass")
        payload["instruments"] = json.dumps(payload.get("instruments", []), ensure_ascii=False)
        payload["start_time"] = self._norm_dt(payload["start_time"])
        payload["end_time"] = self._norm_dt(payload["end_time"])
        payload.setdefault("temperature", None)
        payload.setdefault("pressure", None)
        payload.setdefault("used_by_record_id", None)
        payload["created_at"] = now
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO sterilization_batches (
                        id, batch_number, instruments, sterilizer_id, cycle_type,
                        start_time, end_time, temperature, pressure,
                        indicator_result, operator, expiry_date, used_by_record_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["id"], payload["batch_number"], payload["instruments"],
                        payload["sterilizer_id"], payload["cycle_type"],
                        payload["start_time"], payload["end_time"],
                        payload["temperature"], payload["pressure"],
                        payload["indicator_result"], payload["operator"],
                        payload["expiry_date"], payload["used_by_record_id"],
                        payload["created_at"],
                    ),
                )
        except sqlite3.IntegrityError as e:
            raise ValueError(f"batch_number 重复: {payload.get('batch_number')}") from e
        return self.get_batch(bid) or {}

    def get_batch(self, batch_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sterilization_batches WHERE id=?", (batch_id,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("instruments"):
            try:
                d["instruments"] = json.loads(d["instruments"])
            except json.JSONDecodeError:
                d["instruments"] = []
        return d

    def list_batches(
        self, sterilizer_id: Optional[str] = None
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if sterilizer_id:
                rows = conn.execute(
                    "SELECT * FROM sterilization_batches WHERE sterilizer_id=? ORDER BY start_time DESC",
                    (sterilizer_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM sterilization_batches ORDER BY start_time DESC"
                ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("instruments"):
                try:
                    d["instruments"] = json.loads(d["instruments"])
                except json.JSONDecodeError:
                    d["instruments"] = []
            out.append(d)
        return out

    def expiring_soon(self) -> list[dict[str, Any]]:
        today = datetime.now(timezone.utc).date()
        threshold = today + timedelta(days=self.EXPIRY_ALERT_DAYS)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sterilization_batches "
                "WHERE expiry_date BETWEEN ? AND ? ORDER BY expiry_date",
                (today.isoformat(), threshold.isoformat()),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("instruments"):
                try:
                    d["instruments"] = json.loads(d["instruments"])
                except json.JSONDecodeError:
                    d["instruments"] = []
            out.append(d)
        return out

    def compliance(self, period: str) -> dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT indicator_result, instruments, expiry_date, used_by_record_id "
                "FROM sterilization_batches WHERE substr(start_time,1,7)=?",
                (period,),
            ).fetchall()
        total = len(rows)
        failed = sum(1 for r in rows if r["indicator_result"] == "fail")
        passed = total - failed
        today = datetime.now(timezone.utc).date()
        expired_used = 0
        for r in rows:
            try:
                d = datetime.strptime(r["expiry_date"], "%Y-%m-%d").date()  # noqa: DTZ007
            except (ValueError, TypeError):
                continue
            if r["used_by_record_id"] and d < today:
                expired_used += 1
        instruments_count = 0
        for r in rows:
            try:
                instruments_count += len(json.loads(r["instruments"] or "[]"))
            except json.JSONDecodeError:
                pass
        return {
            "period": period,
            "total_batches": total,
            "pass_rate": round(passed / total, 3) if total else 0.0,
            "failed_batches": failed,
            "expired_used": expired_used,
            "instruments_traced": instruments_count,
        }

    def total_batches(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM sterilization_batches").fetchone()[0])

    def total_sterilizers(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM sterilizers").fetchone()[0])

    @staticmethod
    def _norm_dt(v: Any) -> str:
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)
