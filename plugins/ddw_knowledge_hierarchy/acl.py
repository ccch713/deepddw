"""ACL matrix for three-layer knowledge base permissions (company / department / personal)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.sql.elements import ClauseElement

from .models import KnowledgeBase


@dataclass
class Principal:
    user_id: int
    tenant_id: int
    role: str  # owner / dept_admin / member
    department_id: Optional[int] = None


def can_view(kb: KnowledgeBase, p: Principal) -> bool:
    """Check whether principal can view the knowledge base."""
    if kb.tenant_id != p.tenant_id:
        return False
    if kb.scope == "company":
        return True
    if kb.scope == "department":
        return kb.department_id is not None and kb.department_id == p.department_id
    # personal
    return kb.scope_id == p.user_id


def can_manage(kb: KnowledgeBase, p: Principal) -> bool:
    """Check whether principal can manage (upload/delete documents) the knowledge base."""
    if kb.tenant_id != p.tenant_id:
        return False
    if kb.owner_id == p.user_id:
        return True
    if kb.scope == "company":
        return False
    if kb.scope == "department":
        return p.role == "dept_admin"
    # personal — only owner
    return False


def can_delete_kb(kb: KnowledgeBase, p: Principal) -> bool:
    """Check whether principal can delete the entire knowledge base."""
    if kb.tenant_id != p.tenant_id:
        return False
    if kb.owner_id == p.user_id:
        return True
    if kb.scope == "department":
        return p.role == "dept_admin"
    return False


def visible_kb_filter(p: Principal) -> List[ClauseElement]:
    """Return SQLAlchemy WHERE clauses to filter KBs visible to the principal."""
    company_cond = KnowledgeBase.scope == "company"
    dept_cond = (
        (KnowledgeBase.scope == "department")
        & (KnowledgeBase.department_id == p.department_id)
    )
    personal_cond = (
        (KnowledgeBase.scope == "personal")
        & (KnowledgeBase.scope_id == p.user_id)
    )
    tenant_cond = KnowledgeBase.tenant_id == p.tenant_id
    return [tenant_cond & or_(company_cond, dept_cond, personal_cond)]
