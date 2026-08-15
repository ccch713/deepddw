"""证书 CRUD 业务逻辑。"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_personnel_qual.models import PersonnelCert

logger = logging.getLogger(__name__)


class CertService:
    """证书主表 CRUD + 导入导出。"""

    # ----------------- 单条 ----------------- #

    async def create(self, session: AsyncSession, payload: Dict[str, Any]) -> PersonnelCert:
        cert = PersonnelCert(**payload)
        session.add(cert)
        await session.flush()
        await session.refresh(cert)
        return cert

    async def get(self, session: AsyncSession, cert_id: int) -> Optional[PersonnelCert]:
        return (
            await session.execute(select(PersonnelCert).where(PersonnelCert.id == cert_id))
        ).scalar_one_or_none()

    async def update(self, session: AsyncSession, cert_id: int, patch: Dict[str, Any]) -> Optional[PersonnelCert]:
        cert = await self.get(session, cert_id)
        if cert is None:
            return None
        for k, v in patch.items():
            if v is not None and hasattr(cert, k):
                setattr(cert, k, v)
        await session.flush()
        await session.refresh(cert)
        return cert

    async def delete(self, session: AsyncSession, cert_id: int) -> bool:
        cert = await self.get(session, cert_id)
        if cert is None:
            return False
        await session.delete(cert)
        await session.flush()
        return True

    # ----------------- 列表 ----------------- #

    async def list_by_person(self, session: AsyncSession, person_id: str) -> List[PersonnelCert]:
        return (
            await session.execute(
                select(PersonnelCert).where(PersonnelCert.person_id == person_id).order_by(PersonnelCert.id)
            )
        ).scalars().all()

    async def list(
        self,
        session: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        cert_type: Optional[str] = None,
        status: Optional[str] = None,
        person_name: Optional[str] = None,
    ) -> Tuple[int, List[PersonnelCert]]:
        """分页 + 筛选。返回 (total, items)。"""
        where = []
        if cert_type:
            where.append(PersonnelCert.cert_type == cert_type)
        if status:
            where.append(PersonnelCert.status == status)
        if person_name:
            where.append(PersonnelCert.person_name.like(f"%{person_name}%"))

        count_q = select(func.count(PersonnelCert.id))
        list_q = select(PersonnelCert).order_by(PersonnelCert.id.desc())
        if where:
            count_q = count_q.where(and_(*where))
            list_q = list_q.where(and_(*where))

        total = (await session.execute(count_q)).scalar_one()
        items = (
            await session.execute(list_q.offset((page - 1) * page_size).limit(page_size))
        ).scalars().all()
        return total, list(items)

    # ----------------- 统计 ----------------- #

    async def stats(self, session: AsyncSession) -> Dict[str, Any]:
        rows = (await session.execute(select(PersonnelCert))).scalars().all()
        by_type: Dict[str, int] = {}
        by_level: Dict[str, int] = {}
        total = active = expired = renewing = 0
        for r in rows:
            total += 1
            by_type[r.cert_type] = by_type.get(r.cert_type, 0) + 1
            if r.cert_level:
                by_level[r.cert_level] = by_level.get(r.cert_level, 0) + 1
            if r.status == "active":
                active += 1
            elif r.status == "expired":
                expired += 1
            elif r.status == "renewing":
                renewing += 1
        return {
            "total": total,
            "active": active,
            "expired": expired,
            "renewing": renewing,
            "by_type": by_type,
            "by_level": by_level,
        }

    # ----------------- 导入导出 ----------------- #

    async def import_rows(self, session: AsyncSession, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """批量插入。rows 元素为字段字典。返回 {success, failed, errors}。"""
        success = 0
        failed = 0
        errors: List[Dict[str, Any]] = []
        for idx, row in enumerate(rows):
            try:
                # 日期字符串 -> date 对象
                for d_field in ("issue_date", "expiry_date", "renewal_date"):
                    if isinstance(row.get(d_field), str) and row[d_field]:
                        row[d_field] = date.fromisoformat(row[d_field])
                cert = PersonnelCert(**row)
                session.add(cert)
                success += 1
            except Exception as e:  # noqa: BLE001
                failed += 1
                errors.append({"row": idx, "error": str(e), "data": row})
        if success:
            await session.flush()
        return {"success": success, "failed": failed, "errors": errors}

    async def export_csv(self, session: AsyncSession) -> str:
        rows = (await session.execute(select(PersonnelCert).order_by(PersonnelCert.id))).scalars().all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "id", "person_name", "person_id", "cert_type", "cert_no", "cert_level",
            "issue_org", "issue_date", "expiry_date", "renewal_date", "status", "notes",
        ])
        for r in rows:
            writer.writerow([
                r.id, r.person_name, r.person_id, r.cert_type, r.cert_no, r.cert_level or "",
                r.issue_org or "",
                r.issue_date.isoformat() if r.issue_date else "",
                r.expiry_date.isoformat() if r.expiry_date else "",
                r.renewal_date.isoformat() if r.renewal_date else "",
                r.status, r.notes or "",
            ])
        return output.getvalue()


__all__ = ["CertService"]


# ---- CSV 解析辅助（纯函数，router 直接用） ----

def parse_csv(content: str, skip_header: bool = True) -> Tuple[List[str], List[Dict[str, Any]]]:
    """解析 CSV 文本 → (headers, rows)。

    - skip_header=True: 第一行是表头，返回 (headers, data_rows)
    - skip_header=False: 自动生成 col_0/col_1/... 表头，全部行都是数据
    """
    reader = csv.reader(io.StringIO(content))
    rows_all = [r for r in reader if any(c.strip() for c in r)]
    if not rows_all:
        return [], []
    if skip_header:
        headers = [h.strip() for h in rows_all[0]]
        data_rows = rows_all[1:]
    else:
        # 自动生成列名
        ncols = max(len(r) for r in rows_all)
        headers = [f"col_{i}" for i in range(ncols)]
        data_rows = rows_all
    records: List[Dict[str, Any]] = []
    for r in data_rows:
        padded = r + [""] * (len(headers) - len(r)) if len(r) < len(headers) else r[: len(headers)]
        records.append({h: (v.strip() if isinstance(v, str) else v) for h, v in zip(headers, padded)})
    return headers, records


def to_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)
