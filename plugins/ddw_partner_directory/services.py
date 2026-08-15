from __future__ import annotations

"""DDW 经销商开户插件业务逻辑层。"""

import logging
from typing import Any, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Partner
from .schemas import (
    PartnerCreateReq,
    PartnerListResp,
    PartnerResp,
    PartnerStatsResp,
    PartnerUpdateReq,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _partner_to_dict(p: Partner) -> dict[str, Any]:
    """ORM → dict（用于响应）。"""
    return {
        "id": p.id,
        "tenant_id": p.tenant_id,
        "company_id": p.company_id,
        "partner_type": p.partner_type,
        "level": p.level,
        "region": p.region,
        "industry": p.industry,
        "allowed_products": list(p.allowed_products) if p.allowed_products else [],
        "product_discount": p.product_discount,
        "plugin_discount": p.plugin_discount,
        "service_discount": p.service_discount,
        "agreement_start": p.agreement_start,
        "agreement_end": p.agreement_end,
        "contact_person": p.contact_person,
        "contact_phone": p.contact_phone,
        "status": p.status,
        "notes": p.notes,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
        "created_by": p.created_by,
    }


# ---------------------------------------------------------------------------
# 业务服务
# ---------------------------------------------------------------------------


class PartnerService:
    """经销商开户业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # create
    # ------------------------------------------------------------------ #

    async def create(self, data: PartnerCreateReq) -> dict[str, Any]:
        """新建经销商开户。"""
        partner = Partner(
            tenant_id=data.tenant_id,
            company_id=data.company_id,
            partner_type=data.partner_type,
            level=data.level,
            region=data.region,
            industry=data.industry,
            allowed_products=data.allowed_products or [],
            product_discount=data.product_discount if data.product_discount is not None else 80,
            plugin_discount=data.plugin_discount if data.plugin_discount is not None else 85,
            service_discount=data.service_discount if data.service_discount is not None else 90,
            agreement_start=data.agreement_start,
            agreement_end=data.agreement_end,
            contact_person=data.contact_person,
            contact_phone=data.contact_phone,
            notes=data.notes,
            status="active",
            created_by=data.created_by,
        )
        self.db.add(partner)
        await self.db.commit()
        await self.db.refresh(partner)
        logger.info(
            "partner created: id=%s type=%s level=%s company_id=%s",
            partner.id,
            partner.partner_type,
            partner.level,
            partner.company_id,
        )
        return _partner_to_dict(partner)

    # ------------------------------------------------------------------ #
    # get
    # ------------------------------------------------------------------ #

    async def get(self, partner_id: int) -> dict[str, Any] | None:
        """获取经销商详情。"""
        partner = await self.db.get(Partner, partner_id)
        if not partner:
            return None
        return _partner_to_dict(partner)

    # ------------------------------------------------------------------ #
    # list（分页 + 多维筛选 + 模糊搜索）
    # ------------------------------------------------------------------ #

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        partner_type: Optional[str] = None,
        level: Optional[str] = None,
        region: Optional[str] = None,
        industry: Optional[str] = None,
        status: Optional[str] = None,
    ) -> PartnerListResp:
        """经销商列表（分页 + 筛选 + 搜索）。"""
        conditions = []
        if search:
            like = f"%{search}%"
            conditions.append(
                or_(
                    Partner.contact_person.like(like),
                    Partner.industry.like(like),
                    Partner.region.like(like),
                    Partner.notes.like(like),
                )
            )
        if partner_type:
            conditions.append(Partner.partner_type == partner_type)
        if level:
            conditions.append(Partner.level == level)
        if region:
            conditions.append(Partner.region == region)
        if industry:
            conditions.append(Partner.industry == industry)
        if status:
            conditions.append(Partner.status == status)

        # total
        count_stmt = select(func.count(Partner.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar_one()

        # items
        offset = (page - 1) * page_size
        list_stmt = (
            select(Partner)
            .order_by(Partner.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        if conditions:
            list_stmt = list_stmt.where(and_(*conditions))
        rows = (await self.db.execute(list_stmt)).scalars().all()

        return PartnerListResp(
            total=total,
            page=page,
            page_size=page_size,
            items=[PartnerResp(**_partner_to_dict(p)) for p in rows],
        )

    # ------------------------------------------------------------------ #
    # update
    # ------------------------------------------------------------------ #

    async def update(self, partner_id: int, data: PartnerUpdateReq) -> dict[str, Any] | None:
        """更新经销商字段。"""
        partner = await self.db.get(Partner, partner_id)
        if not partner:
            return None
        updates = data.model_dump(exclude_unset=True)
        for k, v in updates.items():
            setattr(partner, k, v)
        await self.db.commit()
        await self.db.refresh(partner)
        logger.info("partner updated: id=%s", partner.id)
        return _partner_to_dict(partner)

    # ------------------------------------------------------------------ #
    # suspend（软删除）
    # ------------------------------------------------------------------ #

    async def suspend(self, partner_id: int) -> dict[str, Any] | None:
        """暂停经销商（软删除：status=suspended）。"""
        partner = await self.db.get(Partner, partner_id)
        if not partner:
            return None
        partner.status = "suspended"
        await self.db.commit()
        await self.db.refresh(partner)
        logger.info("partner suspended: id=%s", partner.id)
        return _partner_to_dict(partner)

    # ------------------------------------------------------------------ #
    # stats
    # ------------------------------------------------------------------ #

    async def stats(self) -> PartnerStatsResp:
        """统计概览。"""
        # 按 status
        by_status_rows = (
            await self.db.execute(
                select(Partner.status, func.count(Partner.id)).group_by(Partner.status)
            )
        ).all()
        by_status = {s: cnt for s, cnt in by_status_rows}

        # 按 partner_type
        by_type_rows = (
            await self.db.execute(
                select(Partner.partner_type, func.count(Partner.id)).group_by(
                    Partner.partner_type
                )
            )
        ).all()
        by_type = {t: cnt for t, cnt in by_type_rows}

        # 按 level
        by_level_rows = (
            await self.db.execute(
                select(Partner.level, func.count(Partner.id)).group_by(Partner.level)
            )
        ).all()
        by_level = {lvl: cnt for lvl, cnt in by_level_rows}

        # 按 region（排除 NULL）
        by_region_rows = (
            await self.db.execute(
                select(Partner.region, func.count(Partner.id))
                .where(Partner.region.isnot(None))
                .group_by(Partner.region)
            )
        ).all()
        by_region = {r: cnt for r, cnt in by_region_rows}

        total = sum(by_status.values())
        return PartnerStatsResp(
            total=total,
            active=by_status.get("active", 0),
            inactive=by_status.get("inactive", 0),
            suspended=by_status.get("suspended", 0),
            by_partner_type=by_type,
            by_level=by_level,
            by_region=by_region,
        )


__all__ = ["PartnerService"]
