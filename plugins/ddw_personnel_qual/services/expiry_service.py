"""证书到期预警：按 30/60/90 天分档 + 自动写提醒。"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_personnel_qual.models import CertAlert, PersonnelCert

logger = logging.getLogger(__name__)


def _bucket(days_left: int) -> str:
    if days_left < 0:
        return "expired"
    if days_left <= 30:
        return "within_30"
    if days_left <= 60:
        return "within_60"
    if days_left <= 90:
        return "within_90"
    return "ok"


class ExpiryService:
    """到期预警服务。"""

    def __init__(self, warn_days: int = 90) -> None:
        self.warn_days = warn_days

    async def scan(
        self, session: AsyncSession, today: date | None = None, persist: bool = True
    ) -> Dict[str, Any]:
        """扫描所有证书，按到期日分档。

        - days_left < 0  -> expired
        - 0..30          -> within_30
        - 31..60         -> within_60
        - 61..warn_days  -> within_90（默认 90）
        """
        today = today or date.today()
        rows = (await session.execute(select(PersonnelCert))).scalars().all()
        items: List[Dict[str, Any]] = []
        counters = {"within_30": 0, "within_60": 0, "within_90": 0, "expired": 0}

        for cert in rows:
            if cert.expiry_date is None:
                continue
            days_left = (cert.expiry_date - today).days
            bucket = _bucket(days_left)
            if bucket == "ok":
                continue
            counters[bucket] += 1
            items.append({
                "cert_id": cert.id,
                "person_name": cert.person_name,
                "cert_type": cert.cert_type,
                "cert_no": cert.cert_no,
                "expiry_date": cert.expiry_date,
                "days_left": days_left,
                "bucket": bucket,
            })
            if persist and bucket != "ok":
                # 写一条提醒（如不存在同类型）
                await self._upsert_alert(session, cert, bucket, days_left)

        if persist:
            await session.flush()
        return {**counters, "items": items}

    async def _upsert_alert(
        self, session: AsyncSession, cert: PersonnelCert, bucket: str, days_left: int
    ) -> None:
        """同一 cert + bucket 不重复插入。"""
        existing = (
            await session.execute(
                select(CertAlert).where(
                    CertAlert.cert_id == cert.id, CertAlert.alert_type == bucket
                )
            )
        ).scalar_one_or_none()
        if existing:
            return
        severity = "critical" if bucket == "expired" else ("warn" if bucket == "within_30" else "info")
        message = (
            f"【{cert.person_name}】的【{cert.cert_type}】证书"
            f"（编号 {cert.cert_no}）"
            f"{'已过期 ' + str(-days_left) + ' 天' if days_left < 0 else '将在 ' + str(days_left) + ' 天内到期'}"
        )
        alert = CertAlert(
            cert_id=cert.id,
            tenant_id=cert.tenant_id,
            alert_type=bucket,
            severity=severity,
            message=message,
        )
        session.add(alert)

    async def list_alerts(
        self, session: AsyncSession, unread_only: bool = False, limit: int = 100
    ) -> Dict[str, Any]:
        where = []
        if unread_only:
            where.append(CertAlert.is_read == 0)
        q = select(CertAlert).order_by(CertAlert.id.desc()).limit(limit)
        if where:
            from sqlalchemy import and_

            q = q.where(and_(*where))
        rows = (await session.execute(q)).scalars().all()
        total = len(rows)
        unread = sum(1 for r in rows if r.is_read == 0)
        return {
            "total": total,
            "unread": unread,
            "items": [
                {
                    "id": r.id,
                    "cert_id": r.cert_id,
                    "alert_type": r.alert_type,
                    "severity": r.severity,
                    "message": r.message,
                    "is_read": r.is_read,
                    "created_at": r.created_at,
                }
                for r in rows
            ],
        }

    async def mark_read(self, session: AsyncSession, alert_id: int) -> bool:
        from sqlalchemy import update

        result = await session.execute(
            update(CertAlert).where(CertAlert.id == alert_id).values(is_read=1)
        )
        return result.rowcount > 0


__all__ = ["ExpiryService"]
