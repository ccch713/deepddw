"""DDW Informed Consent - 存储."""
from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .models import DEFAULT_TEMPLATES


class ConsentStore:
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
                CREATE TABLE IF NOT EXISTS consent_records (
                    id TEXT PRIMARY KEY,
                    patient_id TEXT NOT NULL,
                    record_id TEXT,
                    consent_type TEXT NOT NULL,
                    template_content TEXT NOT NULL,
                    patient_signature TEXT,
                    signed_at TEXT,
                    witness TEXT,
                    audio_path TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_consent_patient "
                "ON consent_records(patient_id)"
            )

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        cid = data.get("id") or f"ic_{uuid.uuid4().hex[:8]}"
        payload = dict(data)
        payload["id"] = cid
        payload.setdefault("status", "pending")
        payload.setdefault("patient_signature", None)
        payload.setdefault("signed_at", None)
        payload.setdefault("witness", None)
        payload.setdefault("audio_path", None)
        payload.setdefault("record_id", None)
        payload["created_at"] = now
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO consent_records (
                    id, patient_id, record_id, consent_type,
                    template_content, patient_signature, signed_at,
                    witness, audio_path, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(payload[k] for k in [
                    "id", "patient_id", "record_id", "consent_type",
                    "template_content", "patient_signature", "signed_at",
                    "witness", "audio_path", "status", "created_at",
                ]),
            )
        return self.get(cid) or {}

    def get(self, consent_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM consent_records WHERE id=?", (consent_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_for_patient(self, patient_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM consent_records WHERE patient_id=? ORDER BY created_at DESC",
                (patient_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_all(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM consent_records ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def update(
        self, consent_id: str, updates: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        if not updates:
            return self.get(consent_id)
        fields = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [consent_id]
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE consent_records SET {fields} WHERE id=?", tuple(values)
            )
        return self.get(consent_id)

    def total_count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM consent_records").fetchone()[0])

    def list_templates(self) -> list[dict[str, str]]:
        return [dict(t) for t in DEFAULT_TEMPLATES]
