"""Human escalation manager — create, track, and resolve escalation requests."""

import datetime
import uuid
from typing import Optional


class EscalationManager:
    """In-memory escalation tracker.

    In production, data persists via SQLAlchemy ORM.
    """

    def __init__(self):
        self.escalations: dict[str, dict] = {}

    def create_escalation(
        self,
        session_id: str,
        reason: str,
        priority: str = "normal",
        contact_info: Optional[dict] = None,
        context_summary: str = "",
    ) -> dict:
        esc_id = uuid.uuid4().hex[:12]
        now = datetime.datetime.utcnow().isoformat()
        escalation = {
            "id": esc_id,
            "session_id": session_id,
            "reason": reason,
            "priority": priority,
            "status": "pending",
            "assigned_to": None,
            "contact_info": contact_info or {},
            "context_summary": context_summary,
            "estimated_wait_minutes": 15,
            "created_at": now,
            "resolved_at": None,
        }
        self.escalations[esc_id] = escalation
        return escalation

    def get_escalation(self, escalation_id: str) -> Optional[dict]:
        return self.escalations.get(escalation_id)

    def list_escalations(
        self,
        status: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        results = []
        for e in self.escalations.values():
            if status and e["status"] != status:
                continue
            if session_id and e["session_id"] != session_id:
                continue
            results.append(e)
            if len(results) >= limit:
                break
        return results

    def resolve(self, escalation_id: str) -> dict:
        esc = self.escalations.get(escalation_id)
        if esc:
            esc["status"] = "resolved"
            esc["resolved_at"] = datetime.datetime.utcnow().isoformat()
        return esc or {}

    def cancel(self, escalation_id: str) -> dict:
        esc = self.escalations.get(escalation_id)
        if esc:
            esc["status"] = "cancelled"
        return esc or {}
