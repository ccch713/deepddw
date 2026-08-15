"""DDW Dental EMR - 病历存储."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class DentalRecordStore:
    """SQLite 病历存储（线程安全）."""

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
                CREATE TABLE IF NOT EXISTS dental_records (
                    id TEXT PRIMARY KEY,
                    patient_id TEXT NOT NULL,
                    doctor_id TEXT NOT NULL,
                    treatment_type TEXT NOT NULL,
                    chief_complaint TEXT NOT NULL,
                    present_illness TEXT NOT NULL,
                    past_history TEXT,
                    examination TEXT,
                    diagnosis TEXT NOT NULL,
                    treatment_plan TEXT NOT NULL,
                    special_findings TEXT,
                    urgency TEXT DEFAULT 'routine',
                    status TEXT DEFAULT 'draft',
                    transcript_job_id TEXT,
                    images TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_records_patient "
                "ON dental_records(patient_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_records_doctor "
                "ON dental_records(doctor_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_records_treatment "
                "ON dental_records(treatment_type)"
            )

    def create(self, record: dict[str, Any]) -> dict[str, Any]:
        import uuid as _uuid
        rid = record.get("id") or (
            f"emr_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_"
            f"{_uuid.uuid4().hex[:6]}"
        )
        now = datetime.now(timezone.utc).isoformat()
        payload = dict(record)
        payload["id"] = rid
        payload.setdefault("status", "draft")
        payload.setdefault("urgency", "routine")
        payload.setdefault("notes", None)
        payload.setdefault("transcript_job_id", None)
        payload.setdefault("past_history", None)
        payload.setdefault("examination", {})
        payload.setdefault("special_findings", {})
        payload.setdefault("images", [])
        payload["created_at"] = now
        payload["updated_at"] = now
        payload["examination"] = json.dumps(payload.get("examination", {}), ensure_ascii=False)
        payload["special_findings"] = json.dumps(payload.get("special_findings", {}), ensure_ascii=False)
        payload["images"] = json.dumps(payload.get("images", []), ensure_ascii=False)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO dental_records (
                    id, patient_id, doctor_id, treatment_type,
                    chief_complaint, present_illness, past_history, examination,
                    diagnosis, treatment_plan, special_findings, urgency, status,
                    transcript_job_id, images, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(payload[k] for k in [
                    "id", "patient_id", "doctor_id", "treatment_type",
                    "chief_complaint", "present_illness", "past_history", "examination",
                    "diagnosis", "treatment_plan", "special_findings", "urgency", "status",
                    "transcript_job_id", "images", "notes", "created_at", "updated_at",
                ]),
            )
        return self.get(rid) or {}

    def get(self, record_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM dental_records WHERE id=?", (record_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_by_patient(
        self, patient_id: str, page: int = 1, page_size: int = 20
    ) -> dict[str, Any]:
        offset = max(0, (page - 1) * page_size)
        with self._connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM dental_records WHERE patient_id=?",
                (patient_id,),
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM dental_records WHERE patient_id=? "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (patient_id, page_size, offset),
            ).fetchall()
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "records": [self._row_to_dict(r) for r in rows],
        }

    def list_all(
        self,
        *,
        doctor_id: Optional[str] = None,
        treatment_type: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        offset = max(0, (page - 1) * page_size)
        where: list[str] = []
        params: list[Any] = []
        if doctor_id:
            where.append("doctor_id = ?")
            params.append(doctor_id)
        if treatment_type:
            where.append("treatment_type = ?")
            params.append(treatment_type)
        if status:
            where.append("status = ?")
            params.append(status)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        with self._connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM dental_records {where_sql}", tuple(params)
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM dental_records {where_sql} "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                tuple(params + [page_size, offset]),
            ).fetchall()
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "records": [self._row_to_dict(r) for r in rows],
        }

    def update_status(
        self, record_id: str, status: str, notes: Optional[str] = None
    ) -> Optional[dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            if notes is not None:
                conn.execute(
                    "UPDATE dental_records SET status=?, notes=?, updated_at=? WHERE id=?",
                    (status, notes, now, record_id),
                )
            else:
                conn.execute(
                    "UPDATE dental_records SET status=?, updated_at=? WHERE id=?",
                    (status, now, record_id),
                )
        return self.get(record_id)

    def total_count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM dental_records").fetchone()[0])

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        for key in ("examination", "special_findings", "images"):
            v = d.get(key)
            if v is None or v == "":
                d[key] = {} if key in ("examination", "special_findings") else []
                continue
            try:
                d[key] = json.loads(v)
            except json.JSONDecodeError:
                d[key] = {} if key in ("examination", "special_findings") else []
        return d
