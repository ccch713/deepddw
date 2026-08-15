"""Skill manager public API.

The Skill Manager is built on top of the 3-layer dedup module.
It exposes a small, stable interface that the API layer uses.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database.models import Skill
from core.skill_manager.dedup import ThreeLayerDedup, content_hash, trigger_hash

logger = logging.getLogger(__name__)

# Process-wide dedup state. In multi-worker deployments, lift this
# to Redis (or rebuild from the DB on demand).
_dedup = ThreeLayerDedup()


def get_dedup() -> ThreeLayerDedup:
    return _dedup


async def register_skill(
    session: AsyncSession,
    *,
    name: str,
    content: str,
    trigger: Optional[str] = None,
    tenant_id: Optional[int] = None,
) -> Skill:
    """Create a skill or return the existing canonical one if duplicate."""

    dedup = get_dedup()
    result = dedup.check(content=content, trigger=trigger)
    if result.is_duplicate and result.canonical_id is not None:
        existing = await session.get(Skill, result.canonical_id)
        if existing is not None:
            return existing
    skill = Skill(name=name, content=content, trigger=trigger, tenant_id=tenant_id, embedding_hash=content_hash(content))
    session.add(skill)
    await session.flush()
    dedup.register(canonical_id=skill.id, content=content, trigger=trigger)
    return skill


async def list_skills(session: AsyncSession, *, tenant_id: Optional[int] = None) -> List[Skill]:
    stmt = select(Skill)
    if tenant_id is not None:
        stmt = stmt.where(Skill.tenant_id == tenant_id)
    return list((await session.scalars(stmt)).all())
