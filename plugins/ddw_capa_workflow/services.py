"""Business logic for CAPA Workflow plugin."""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .models import CAPA, CAPAHistory

# Valid state transitions
VALID_TRANSITIONS = {
    "open": ["investigation", "rejected"],
    "investigation": ["action", "rejected"],
    "action": ["verification"],
    "verification": ["closed", "investigation"],  # can reopen if verification fails
    "closed": [],
    "rejected": [],
}


class CAPAService:
    """Core service for CAPA workflow management."""

    def __init__(self, db_session: Session, llm_client: Any = None):
        self.db = db_session
        self.llm = llm_client
        self._counter = 0

    # === CAPA CRUD ===

    def create_capa(self, title: str, description: str, source: str,
                    severity: str = "major", category: str = "general",
                    assigned_to: str = "", due_date: Optional[datetime.datetime] = None,
                    created_by: str = "system") -> CAPA:
        """Create a new CAPA record."""
        capa_number = self._generate_capa_number()
        capa = CAPA(
            capa_number=capa_number, title=title, description=description,
            source=source, severity=severity, category=category,
            assigned_to=assigned_to, due_date=due_date, created_by=created_by,
            status="open",
        )
        self.db.add(capa)
        self.db.commit()
        self.db.refresh(capa)

        # Create initial history
        self._add_history(capa.id, "", "open", f"CAPA创建: {title}", created_by)
        return capa

    def get_capa(self, capa_id: int) -> Optional[CAPA]:
        return self.db.query(CAPA).get(capa_id)

    def get_capa_by_number(self, capa_number: str) -> Optional[CAPA]:
        return self.db.query(CAPA).filter_by(capa_number=capa_number).first()

    def list_capas(self, status: Optional[str] = None, severity: Optional[str] = None,
                   source: Optional[str] = None, assigned_to: Optional[str] = None,
                   limit: int = 50, offset: int = 0) -> List[CAPA]:
        q = self.db.query(CAPA)
        if status:
            q = q.filter(CAPA.status == status)
        if severity:
            q = q.filter(CAPA.severity == severity)
        if source:
            q = q.filter(CAPA.source == source)
        if assigned_to:
            q = q.filter(CAPA.assigned_to == assigned_to)
        return q.order_by(CAPA.created_at.desc()).offset(offset).limit(limit).all()

    # === State Machine ===

    def transition(self, capa_id: int, to_status: str, comment: str = "",
                   changed_by: str = "system") -> Optional[CAPA]:
        """Transition CAPA to a new status with validation."""
        capa = self.db.query(CAPA).get(capa_id)
        if not capa:
            return None

        allowed = VALID_TRANSITIONS.get(capa.status, [])
        if to_status not in allowed:
            raise ValueError(
                f"Invalid transition: {capa.status} -> {to_status}. "
                f"Allowed: {allowed}")

        old_status = capa.status
        capa.status = to_status

        if to_status == "closed":
            capa.closed_at = datetime.datetime.utcnow()

        self.db.commit()
        self._add_history(capa_id, old_status, to_status, comment, changed_by)
        self.db.refresh(capa)
        return capa

    def add_investigation(self, capa_id: int, root_cause: str,
                          method: str = "5why",
                          changed_by: str = "system") -> Optional[CAPA]:
        """Add investigation findings to CAPA."""
        capa = self.db.query(CAPA).get(capa_id)
        if not capa:
            return None
        capa.root_cause = root_cause
        capa.root_cause_method = method
        self.db.commit()
        self._add_history(capa_id, capa.status, capa.status,
                          f"根本原因分析已更新 (方法: {method})", changed_by)
        self.db.refresh(capa)
        return capa

    def add_actions(self, capa_id: int, corrective: str = "",
                    preventive: str = "",
                    changed_by: str = "system") -> Optional[CAPA]:
        """Add corrective and preventive actions."""
        capa = self.db.query(CAPA).get(capa_id)
        if not capa:
            return None
        if corrective:
            capa.corrective_action = corrective
        if preventive:
            capa.preventive_action = preventive
        self.db.commit()
        self._add_history(capa_id, capa.status, capa.status,
                          "纠正/预防措施已更新", changed_by)
        self.db.refresh(capa)
        return capa

    def add_effectiveness_check(self, capa_id: int, check_result: str,
                                 changed_by: str = "system") -> Optional[CAPA]:
        """Add effectiveness verification result."""
        capa = self.db.query(CAPA).get(capa_id)
        if not capa:
            return None
        capa.effectiveness_check = check_result
        self.db.commit()
        self._add_history(capa_id, capa.status, capa.status,
                          f"有效性验证: {check_result[:100]}", changed_by)
        self.db.refresh(capa)
        return capa

    # === Analytics ===

    def get_statistics(self) -> Dict:
        """Get CAPA statistics overview."""
        all_capas = self.db.query(CAPA).all()
        total = len(all_capas)
        by_status = {}
        by_severity = {}
        by_source = {}
        overdue = 0
        now = datetime.datetime.utcnow()

        for c in all_capas:
            by_status[c.status] = by_status.get(c.status, 0) + 1
            by_severity[c.severity] = by_severity.get(c.severity, 0) + 1
            by_source[c.source] = by_source.get(c.source, 0) + 1
            if c.due_date and c.due_date < now and c.status not in ("closed", "rejected"):
                overdue += 1

        return {"total": total, "by_status": by_status, "by_severity": by_severity,
                "by_source": by_source, "overdue": overdue}

    def get_overdue_capas(self) -> List[CAPA]:
        """Get all overdue CAPAs."""
        now = datetime.datetime.utcnow()
        return self.db.query(CAPA).filter(
            CAPA.due_date < now,
            CAPA.status.notin_(["closed", "rejected"])
        ).all()

    def get_history(self, capa_id: int) -> List[CAPAHistory]:
        """Get CAPA history/audit trail."""
        return self.db.query(CAPAHistory).filter_by(capa_id=capa_id).order_by(
            CAPAHistory.created_at).all()

    # === Internal ===

    def _generate_capa_number(self) -> str:
        year = datetime.datetime.utcnow().year
        count = self.db.query(CAPA).filter(
            CAPA.capa_number.like(f"CAPA-{year}-%")
        ).count()
        return f"CAPA-{year}-{count + 1:03d}"

    def _add_history(self, capa_id, from_status, to_status, comment, changed_by):
        h = CAPAHistory(capa_id=capa_id, from_status=from_status,
                        to_status=to_status, comment=comment, changed_by=changed_by)
        self.db.add(h)
        self.db.commit()
