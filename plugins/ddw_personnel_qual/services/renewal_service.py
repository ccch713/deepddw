"""年检追踪：发起年检、状态更新、查询。"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_personnel_qual.models import CertRenewal, PersonnelCert

logger = logging.getLogger(__name__)


class RenewalService:
    """年检服务。"""

    async def create(self, session: AsyncSession, payload: Dict[str, Any]) -> CertRenewal:
        renewal = CertRenewal(**payload)
        session.add(renewal)
        await session.flush()
        await session.refresh(renewal)

        # 同步：cert 状态 -> renewing，并把 renewal_date 写到 cert
        cert = (
            await session.execute(
                select(PersonnelCert).where(PersonnelCert.id == payload["cert_id"])
            )
        ).scalar_one_or_none()
        if cert is not None:
            cert.status = "renewing"
            cert.renewal_date = payload["renewal_date"]
        await session.flush()
        return renewal

    async def update(
        self, session: AsyncSession, renewal_id: int, patch: Dict[str, Any]
    ) -> Optional[CertRenewal]:
        r = (
            await session.execute(select(CertRenewal).where(CertRenewal.id == renewal_id))
        ).scalar_one_or_none()
        if r is None:
            return None
        for k, v in patch.items():
            if v is not None and hasattr(r, k):
                setattr(r, k, v)
        await session.flush()
        await session.refresh(r)

        # 同步 cert 状态
        if r.status == "passed":
            cert = (
                await session.execute(
                    select(PersonnelCert).where(PersonnelCert.id == r.cert_id)
                )
            ).scalar_one_or_none()
            if cert is not None:
                cert.status = "active"
        return r

    async def list(
        self,
        session: AsyncSession,
        cert_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        where = []
        if cert_id is not None:
            where.append(CertRenewal.cert_id == cert_id)
        if status is not None:
            where.append(CertRenewal.status == status)
        q = select(CertRenewal).order_by(CertRenewal.id.desc()).limit(limit)
        if where:
            from sqlalchemy import and_

            q = q.where(and_(*where))
        rows = (await session.execute(q)).scalars().all()
        return {
            "total": len(rows),
            "items": [
                {
                    "id": r.id,
                    "tenant_id": r.tenant_id,
                    "cert_id": r.cert_id,
                    "renewal_date": r.renewal_date,
                    "result": r.result,
                    "operator": r.operator,
                    "notes": r.notes,
                    "status": r.status,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                }
                for r in rows
            ],
        }


__all__ = ["RenewalService"]
