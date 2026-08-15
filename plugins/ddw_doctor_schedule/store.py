"""DDW Doctor Schedule - 存储."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class DoctorStore:
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
                CREATE TABLE IF NOT EXISTS doctors (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    title TEXT,
                    specialty TEXT,
                    phone TEXT,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schedule_slots (
                    id TEXT PRIMARY KEY,
                    doctor_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    slot_type TEXT DEFAULT 'normal',
                    max_patients INTEGER DEFAULT 10,
                    booked_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_slots_doctor_date "
                "ON schedule_slots(doctor_id, date)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_slots_date "
                "ON schedule_slots(date)"
            )

    def create_doctor(self, data: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        did = data.get("id") or f"doc_{uuid.uuid4().hex[:6]}"
        payload = dict(data)
        payload["id"] = did
        payload.setdefault("is_active", True)
        payload["specialty"] = json.dumps(payload.get("specialty", []), ensure_ascii=False)
        payload["created_at"] = now
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO doctors (id, name, title, specialty, phone, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["id"], payload["name"], payload.get("title"),
                    payload["specialty"], payload.get("phone"),
                    int(payload["is_active"]), payload["created_at"],
                ),
            )
        return self.get_doctor(did) or {}

    def get_doctor(self, doctor_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM doctors WHERE id=?", (doctor_id,)
            ).fetchone()
        return self._doc_to_dict(row) if row else None

    def list_doctors(self, active_only: bool = False) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if active_only:
                rows = conn.execute(
                    "SELECT * FROM doctors WHERE is_active=1 ORDER BY name"
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM doctors ORDER BY name").fetchall()
        return [self._doc_to_dict(r) for r in rows]

    def update_doctor(self, doctor_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
        if not updates:
            return self.get_doctor(doctor_id)
        if "is_active" in updates:
            updates["is_active"] = int(bool(updates["is_active"]))
        if "specialty" in updates and isinstance(updates["specialty"], list):
            updates["specialty"] = json.dumps(updates["specialty"], ensure_ascii=False)
        fields = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [doctor_id]
        with self._lock, self._connect() as conn:
            conn.execute(f"UPDATE doctors SET {fields} WHERE id=?", tuple(values))
        return self.get_doctor(doctor_id)

    # --- slots ---

    def create_slot(self, data: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        sid = data.get("id") or f"slot_{uuid.uuid4().hex[:8]}"
        payload = dict(data)
        payload["id"] = sid
        payload.setdefault("slot_type", "normal")
        payload.setdefault("max_patients", 10)
        payload.setdefault("booked_count", 0)
        payload["created_at"] = now
        with self._lock, self._connect() as conn:
            # 同医生同时段冲突检测
            existing = conn.execute(
                """
                SELECT id FROM schedule_slots
                WHERE doctor_id=? AND date=? AND start_time=? AND slot_type IN ('normal','on_call')
                """,
                (payload["doctor_id"], payload["date"], payload["start_time"]),
            ).fetchone()
            if existing:
                raise ValueError(
                    f"排班冲突: doctor={payload['doctor_id']} "
                    f"date={payload['date']} time={payload['start_time']}"
                )
            conn.execute(
                """
                INSERT INTO schedule_slots
                (id, doctor_id, date, start_time, end_time, slot_type,
                 max_patients, booked_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["id"], payload["doctor_id"], payload["date"],
                    payload["start_time"], payload["end_time"],
                    payload["slot_type"], payload["max_patients"],
                    payload["booked_count"], payload["created_at"],
                ),
            )
        return self.get_slot(sid) or {}

    def get_slot(self, slot_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM schedule_slots WHERE id=?", (slot_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_slots(
        self,
        date: Optional[str] = None,
        doctor_id: Optional[str] = None,
        week: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if date:
            where.append("date = ?")
            params.append(date)
        if doctor_id:
            where.append("doctor_id = ?")
            params.append(doctor_id)
        if week:
            # week=2026-W33 简化为按 date in (...)
            start, end = _week_to_range(week)
            where.append("date BETWEEN ? AND ?")
            params.extend([start, end])
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        sql = f"SELECT * FROM schedule_slots {where_sql} ORDER BY date, start_time"
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]

    def update_slot(self, slot_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
        if not updates:
            return self.get_slot(slot_id)
        fields = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [slot_id]
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE schedule_slots SET {fields} WHERE id=?", tuple(values)
            )
        return self.get_slot(slot_id)

    def total_doctors(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM doctors").fetchone()[0])

    def total_slots(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM schedule_slots").fetchone()[0])

    @staticmethod
    def _doc_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        sp = d.get("specialty")
        if sp:
            try:
                d["specialty"] = json.loads(sp)
            except json.JSONDecodeError:
                d["specialty"] = []
        else:
            d["specialty"] = []
        d["is_active"] = bool(d.get("is_active", 1))
        return d


def _week_to_range(week: str) -> tuple[str, str]:
    """ISO week YYYY-Www -> (monday, sunday) YYYY-MM-DD."""
    try:
        year_s, w_s = week.split("-W")
        from datetime import date
        monday = date.fromisocalendar(int(year_s), int(w_s), 1)
        sunday = date.fromordinal(monday.toordinal() + 6)
        return monday.isoformat(), sunday.isoformat()
    except (ValueError, AttributeError):
        return "0000-00-00", "9999-99-99"
