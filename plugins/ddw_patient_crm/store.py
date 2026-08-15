"""DDW Patient CRM - 存储."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class PatientStore:
    """SQLite 患者档案存储."""

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
                CREATE TABLE IF NOT EXISTS patients (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    phone TEXT NOT NULL UNIQUE,
                    gender TEXT,
                    birth_date TEXT,
                    source TEXT DEFAULT 'unknown',
                    tags TEXT,
                    allergies TEXT,
                    medical_history TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_patients_phone ON patients(phone)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_patients_name ON patients(name)"
            )

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        pid = data.get("id") or f"pt_{uuid.uuid4().hex[:8]}"
        payload = dict(data)
        payload["id"] = pid
        payload.setdefault("source", "unknown")
        payload.setdefault("gender", None)
        payload.setdefault("birth_date", None)
        payload.setdefault("medical_history", None)
        payload.setdefault("notes", None)
        payload["tags"] = json.dumps(payload.get("tags", []), ensure_ascii=False)
        payload["allergies"] = json.dumps(payload.get("allergies", []), ensure_ascii=False)
        payload["created_at"] = now
        payload["updated_at"] = now
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO patients (
                        id, name, phone, gender, birth_date, source,
                        tags, allergies, medical_history, notes,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    tuple(payload[k] for k in [
                        "id", "name", "phone", "gender", "birth_date", "source",
                        "tags", "allergies", "medical_history", "notes",
                        "created_at", "updated_at",
                    ]),
                )
        except sqlite3.IntegrityError as e:
            raise ValueError(f"phone 重复: {payload.get('phone')}") from e
        return self.get(pid) or {}

    def get(self, patient_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM patients WHERE id=?", (patient_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_by_phone(self, phone: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM patients WHERE phone=?", (phone,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def search(
        self,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        tag: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        where: list[str] = []
        params: list[Any] = []
        if name:
            where.append("name LIKE ?")
            params.append(f"%{name}%")
        if phone:
            where.append("phone = ?")
            params.append(phone)
        if tag:
            where.append("tags LIKE ?")
            params.append(f'%"{tag}"%')
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        offset = max(0, (page - 1) * page_size)
        with self._connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM patients {where_sql}", tuple(params)
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM patients {where_sql} "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                tuple(params + [page_size, offset]),
            ).fetchall()
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "patients": [self._row_to_dict(r) for r in rows],
        }

    def update(self, patient_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
        if not updates:
            return self.get(patient_id)
        now = datetime.now(timezone.utc).isoformat()
        fields: list[str] = []
        values: list[Any] = []
        for k, v in updates.items():
            if k in ("tags", "allergies") and isinstance(v, list):
                v = json.dumps(v, ensure_ascii=False)
            fields.append(f"{k} = ?")
            values.append(v)
        fields.append("updated_at = ?")
        values.append(now)
        values.append(patient_id)
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    f"UPDATE patients SET {', '.join(fields)} WHERE id=?",
                    tuple(values),
                )
        except sqlite3.IntegrityError as e:
            raise ValueError(f"phone 重复: {updates.get('phone')}") from e
        return self.get(patient_id)

    def stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
            this_month = datetime.now(timezone.utc).strftime("%Y-%m")
            this_month_count = conn.execute(
                "SELECT COUNT(*) FROM patients WHERE substr(created_at,1,7) = ?",
                (this_month,),
            ).fetchone()[0]
            by_source: dict[str, int] = {}
            for row in conn.execute(
                "SELECT source, COUNT(*) c FROM patients GROUP BY source"
            ).fetchall():
                by_source[row["source"]] = int(row["c"])
            by_gender: dict[str, int] = {}
            for row in conn.execute(
                "SELECT COALESCE(gender, 'unknown') g, COUNT(*) c FROM patients GROUP BY gender"
            ).fetchall():
                by_gender[row["g"]] = int(row["c"])
        return {
            "total_patients": total,
            "this_month_new": this_month_count,
            "by_source": by_source,
            "by_gender": by_gender,
        }

    def list_visits(self, patient_id: str) -> list[dict[str, Any]]:
        """跨插件读 dental_emr 库的病历（如有）.

        查找顺序：
        1. 同 db 父目录下的 dental_emr.db（开发/测试同 data 目录）
        2. ../ddw_dental_emr/data/dental_emr.db（生产部署的兄弟插件目录）
        """
        candidates = [
            self.db_path.parent / "dental_emr.db",
            self.db_path.parent.parent / "ddw_dental_emr" / "data" / "dental_emr.db",
        ]
        for sibling_db in candidates:
            if not sibling_db.exists():
                continue
            try:
                with sqlite3.connect(sibling_db, timeout=5) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(
                        "SELECT id, treatment_type, diagnosis, doctor_id, created_at, status "
                        "FROM dental_records WHERE patient_id=? ORDER BY created_at DESC",
                        (patient_id,),
                    ).fetchall()
                # 把 id 映射成 record_id，对齐 VisitSummary
                return [
                    {**dict(r), "record_id": r["id"]} for r in rows
                ]
            except sqlite3.Error:
                continue
        return []

    def total_count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0])

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        for key in ("tags", "allergies"):
            v = d.get(key)
            if v is None or v == "":
                d[key] = []
                continue
            try:
                d[key] = json.loads(v)
            except json.JSONDecodeError:
                d[key] = []
        return d
