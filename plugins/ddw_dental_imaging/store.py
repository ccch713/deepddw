"""DDW Dental Imaging - 存储."""
from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class ImageStore:
    def __init__(self, db_path: Path, root_dir: Path) -> None:
        self.db_path = Path(db_path)
        self.root_dir = Path(root_dir)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.root_dir.mkdir(parents=True, exist_ok=True)
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
                CREATE TABLE IF NOT EXISTS dental_images (
                    id TEXT PRIMARY KEY,
                    patient_id TEXT NOT NULL,
                    record_id TEXT,
                    image_type TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_size INTEGER DEFAULT 0,
                    taken_at TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_images_patient "
                "ON dental_images(patient_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_images_type "
                "ON dental_images(image_type)"
            )

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        iid = data.get("id") or f"img_{uuid.uuid4().hex[:8]}"
        payload = dict(data)
        payload["id"] = iid
        payload.setdefault("file_size", 0)
        payload.setdefault("taken_at", None)
        payload.setdefault("record_id", None)
        payload.setdefault("notes", None)
        payload["created_at"] = now
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO dental_images (
                    id, patient_id, record_id, image_type, file_path,
                    file_size, taken_at, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(payload[k] for k in [
                    "id", "patient_id", "record_id", "image_type", "file_path",
                    "file_size", "taken_at", "notes", "created_at",
                ]),
            )
        return self.get(iid) or {}

    def get(self, image_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM dental_images WHERE id=?", (image_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_for_patient(
        self,
        patient_id: str,
        image_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if image_type:
                rows = conn.execute(
                    "SELECT * FROM dental_images "
                    "WHERE patient_id=? AND image_type=? "
                    "ORDER BY created_at DESC",
                    (patient_id, image_type),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM dental_images WHERE patient_id=? "
                    "ORDER BY created_at DESC",
                    (patient_id,),
                ).fetchall()
        return [dict(r) for r in rows]

    def timeline(self, patient_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM dental_images WHERE patient_id=? "
                "ORDER BY COALESCE(taken_at, created_at)",
                (patient_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete(self, image_id: str) -> bool:
        img = self.get(image_id)
        if img is None:
            return False
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM dental_images WHERE id=?", (image_id,))
        # 物理删文件
        try:
            p = Path(img["file_path"])
            if p.exists():
                p.unlink()
        except OSError:
            pass
        return True

    def total_count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM dental_images").fetchone()[0])
