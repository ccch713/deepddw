"""DDW Followup - 存储."""
from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DEFAULT_TEMPLATES = [
    {
        "name": "拔牙术后关怀",
        "followup_type": "postop_recall",
        "delay_days": 1,
        "message_template": "您好～昨天的拔牙手术恢复还好吗？如果还有疼痛或出血，请及时联系我们。记得今天吃软食、避免用吸管哦～🦷",
    },
    {
        "name": "根管治疗复诊",
        "followup_type": "postop_recall",
        "delay_days": 7,
        "message_template": "您好～上次根管治疗后感觉怎么样？记得按时回来复诊哦，下次时间约好了吗？😊",
    },
    {
        "name": "种植术后关怀",
        "followup_type": "postop_recall",
        "delay_days": 3,
        "message_template": "您好～种植手术后第3天了，肿胀应该在消退中。如果有异常疼痛或发热，请尽快联系门诊。保持口腔清洁，漱口水按时用～🌿",
    },
    {
        "name": "满意度回访",
        "followup_type": "satisfaction",
        "delay_days": 7,
        "message_template": "您好～感谢您选择东华口腔。方便花 1 分钟告诉我们您的就诊体验吗？您的反馈对我们非常重要～🙏",
    },
]


class FollowupStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()
        self.seed_default_templates()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS followup_tasks (
                    id TEXT PRIMARY KEY,
                    patient_id TEXT NOT NULL,
                    doctor_id TEXT,
                    record_id TEXT,
                    followup_type TEXT NOT NULL,
                    due_date TEXT NOT NULL,
                    message_template TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    channel TEXT DEFAULT 'wechat',
                    created_at TEXT NOT NULL,
                    sent_at TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_status "
                "ON followup_tasks(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_patient_type "
                "ON followup_tasks(patient_id, followup_type)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS followup_templates (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    followup_type TEXT NOT NULL,
                    delay_days INTEGER NOT NULL,
                    message_template TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1
                )
                """
            )

    def seed_default_templates(self) -> None:
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT COUNT(*) FROM followup_templates"
            ).fetchone()[0]
            if existing > 0:
                return
            for tpl in DEFAULT_TEMPLATES:
                tid = f"tpl_{uuid.uuid4().hex[:6]}"
                conn.execute(
                    """
                    INSERT INTO followup_templates
                    (id, name, followup_type, delay_days, message_template, is_active)
                    VALUES (?, ?, ?, ?, ?, 1)
                    """,
                    (tid, tpl["name"], tpl["followup_type"],
                     tpl["delay_days"], tpl["message_template"]),
                )

    def create_task(self, data: dict[str, Any]) -> dict[str, Any]:
        # 去重：同 patient_id + followup_type + pending 不重复
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT id FROM followup_tasks
                WHERE patient_id=? AND followup_type=? AND status='pending'
                """,
                (data["patient_id"], data["followup_type"]),
            ).fetchone()
        if existing:
            return self.get_task(existing["id"]) or {}
        now = datetime.now(timezone.utc).isoformat()
        tid = data.get("id") or f"task_{uuid.uuid4().hex[:8]}"
        payload = dict(data)
        payload["id"] = tid
        payload.setdefault("status", "pending")
        payload.setdefault("channel", "wechat")
        payload.setdefault("sent_at", None)
        payload["created_at"] = now
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO followup_tasks (
                    id, patient_id, doctor_id, record_id, followup_type,
                    due_date, message_template, status, channel, created_at, sent_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(payload[k] for k in [
                    "id", "patient_id", "doctor_id", "record_id", "followup_type",
                    "due_date", "message_template", "status", "channel",
                    "created_at", "sent_at",
                ]),
            )
        return self.get_task(tid) or {}

    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM followup_tasks WHERE id=?", (task_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_tasks(self, status: Optional[str] = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM followup_tasks WHERE status=? ORDER BY due_date",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM followup_tasks ORDER BY due_date"
                ).fetchall()
        return [dict(r) for r in rows]

    def update_task(
        self, task_id: str, updates: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        if not updates:
            return self.get_task(task_id)
        fields = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [task_id]
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE followup_tasks SET {fields} WHERE id=?", tuple(values)
            )
        return self.get_task(task_id)

    # --- templates ---

    def list_templates(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM followup_templates ORDER BY followup_type, delay_days"
            ).fetchall()
        return [dict(r) for r in rows]

    def create_template(self, data: dict[str, Any]) -> dict[str, Any]:
        tid = data.get("id") or f"tpl_{uuid.uuid4().hex[:6]}"
        payload = dict(data)
        payload["id"] = tid
        payload.setdefault("is_active", True)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO followup_templates
                (id, name, followup_type, delay_days, message_template, is_active)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["id"], payload["name"], payload["followup_type"],
                    payload["delay_days"], payload["message_template"],
                    int(payload["is_active"]),
                ),
            )
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM followup_templates WHERE id=?", (tid,)
            ).fetchone()
        return dict(row) if row else {}

    def total_tasks(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM followup_tasks").fetchone()[0])

    def stats(self, period: str) -> dict[str, Any]:
        """统计指定月份 (YYYY-MM)."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT followup_type, status, COUNT(*) c
                FROM followup_tasks
                WHERE substr(created_at,1,7) = ?
                GROUP BY followup_type, status
                """,
                (period,),
            ).fetchall()
        by_type: dict[str, dict[str, int]] = {}
        total = sent = responded = 0
        for r in rows:
            ft = r["followup_type"]
            if ft not in by_type:
                by_type[ft] = {"count": 0, "sent": 0, "responded": 0}
            by_type[ft]["count"] += int(r["c"])
            total += int(r["c"])
            if r["status"] == "sent":
                by_type[ft]["sent"] += int(r["c"])
                sent += int(r["c"])
            elif r["status"] == "responded":
                by_type[ft]["responded"] += int(r["c"])
                responded += int(r["c"])
                # responded 算 sent
                by_type[ft]["sent"] += int(r["c"])
                sent += int(r["c"])
        return {
            "period": period,
            "total_tasks": total,
            "sent": sent,
            "responded": responded,
            "response_rate": round(responded / sent, 3) if sent else 0.0,
            "by_type": by_type,
        }
