"""DDW Talk A1 ASR - 转写任务存储.

轻量 SQLite 存储（stdlib）。记录：
- 任务队列
- 转写结果（每条 job_id 对应一段转写 + 段落数组）
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import config


class JobStore:
    """线程安全的转写任务存储."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path) if db_path else config.DB_PATH
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
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    audio_path TEXT NOT NULL,
                    doctor_id TEXT,
                    patient_name TEXT,
                    session_type TEXT,
                    status TEXT NOT NULL,
                    progress REAL DEFAULT 0.0,
                    error TEXT,
                    full_text TEXT,
                    duration_seconds REAL,
                    language TEXT,
                    model TEXT,
                    segments TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_doctor ON jobs(doctor_id)"
            )

    def create_job(
        self,
        job_id: str,
        audio_path: str,
        doctor_id: Optional[str] = None,
        patient_name: Optional[str] = None,
        session_type: Optional[str] = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, audio_path, doctor_id, patient_name, session_type,
                    status, progress, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'queued', 0.0, ?, ?)
                """,
                (job_id, audio_path, doctor_id, patient_name, session_type, now, now),
            )
        return {
            "job_id": job_id,
            "audio_path": audio_path,
            "doctor_id": doctor_id,
            "patient_name": patient_name,
            "session_type": session_type,
            "status": "queued",
            "progress": 0.0,
            "created_at": now,
            "updated_at": now,
        }

    def update_status(
        self,
        job_id: str,
        status: str,
        *,
        progress: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        if status not in config.JOB_STATUSES:
            raise ValueError(f"invalid status: {status}")
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            if progress is not None and error is not None:
                conn.execute(
                    "UPDATE jobs SET status=?, progress=?, error=?, updated_at=? WHERE job_id=?",
                    (status, progress, error, now, job_id),
                )
            elif progress is not None:
                conn.execute(
                    "UPDATE jobs SET status=?, progress=?, updated_at=? WHERE job_id=?",
                    (status, progress, now, job_id),
                )
            elif error is not None:
                conn.execute(
                    "UPDATE jobs SET status=?, error=?, updated_at=? WHERE job_id=?",
                    (status, error, now, job_id),
                )
            else:
                conn.execute(
                    "UPDATE jobs SET status=?, updated_at=? WHERE job_id=?",
                    (status, now, job_id),
                )

    def save_result(
        self,
        job_id: str,
        full_text: str,
        segments: list[dict[str, Any]],
        duration_seconds: float,
        language: str,
        model: str,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs SET
                    status='completed', progress=1.0,
                    full_text=?, segments=?, duration_seconds=?,
                    language=?, model=?, error=NULL, updated_at=?
                WHERE job_id=?
                """,
                (
                    full_text,
                    json.dumps(segments, ensure_ascii=False),
                    duration_seconds,
                    language,
                    model,
                    now,
                    job_id,
                ),
            )

    def get(self, job_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                return None
            return self._row_to_dict(row)

    def list_by_status(self, status: Optional[str] = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE status=? ORDER BY created_at", (status,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM jobs ORDER BY created_at"
                ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def queue_size(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM jobs WHERE status IN ('queued','transcribing')"
            ).fetchone()
            return int(row["c"]) if row else 0

    def total_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM jobs").fetchone()
            return int(row["c"]) if row else 0

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        if d.get("segments"):
            try:
                d["segments"] = json.loads(d["segments"])
            except json.JSONDecodeError:
                d["segments"] = []
        else:
            d["segments"] = []
        return d
