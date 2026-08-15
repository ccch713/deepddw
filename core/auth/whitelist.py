"""Whitelist management (PRD §7.2.2).

In a closed beta or enterprise deployment, only pre-approved
phone numbers are allowed to register. The whitelist is the
source of truth.

This module exposes helpers to add / remove / list whitelist
entries; the actual API endpoint is in
``core.auth.api`` (added in phase 1.6).
"""

from __future__ import annotations

import logging
from typing import Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database.models import WhitelistEntry

logger = logging.getLogger(__name__)


async def add_entry(
    session: AsyncSession,
    phone: str,
    *,
    tenant_id: Optional[int] = None,
    note: Optional[str] = None,
    added_by: Optional[int] = None,
) -> WhitelistEntry:
    """Add a phone to the whitelist. Idempotent on (phone, tenant_id)."""

    existing = await session.scalar(
        select(WhitelistEntry).where(
            WhitelistEntry.phone == phone,
            WhitelistEntry.tenant_id == tenant_id,
        )
    )
    if existing is not None:
        return existing
    entry = WhitelistEntry(phone=phone, tenant_id=tenant_id, note=note, added_by=added_by)
    session.add(entry)
    await session.flush()
    return entry


async def remove_entry(session: AsyncSession, phone: str, *, tenant_id: Optional[int] = None) -> bool:
    """Remove a phone from the whitelist. Returns True if a row was deleted."""

    existing = await session.scalar(
        select(WhitelistEntry).where(
            WhitelistEntry.phone == phone,
            WhitelistEntry.tenant_id == tenant_id,
        )
    )
    if existing is None:
        return False
    await session.delete(existing)
    return True


async def is_whitelisted(session: AsyncSession, phone: str, *, tenant_id: Optional[int] = None) -> bool:
    """Return True if the phone is on the whitelist (or whitelist is empty)."""

    stmt = select(WhitelistEntry.id).where(WhitelistEntry.tenant_id == tenant_id)
    any_in_tenant = await session.scalar(stmt.limit(1))
    if any_in_tenant is None:
        # No whitelist configured for this tenant => open registration.
        return True
    hit = await session.scalar(
        select(WhitelistEntry.id).where(
            WhitelistEntry.phone == phone,
            WhitelistEntry.tenant_id == tenant_id,
        )
    )
    return hit is not None


async def list_entries(session: AsyncSession, *, tenant_id: Optional[int] = None) -> List[WhitelistEntry]:
    stmt = select(WhitelistEntry)
    if tenant_id is not None:
        stmt = stmt.where(WhitelistEntry.tenant_id == tenant_id)
    return list((await session.scalars(stmt)).all())
