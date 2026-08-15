from __future__ import annotations

"""DDW 企业主体管理插件业务逻辑层。"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Company
from .schemas import (
    CompanyCreateReq,
    CompanyListResp,
    CompanyResp,
    CompanyStatsResp,
    CompanyUpdateReq,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _company_to_dict(c: Company) -> Dict[str, Any]:
    """ORM → dict（用于响应）。"""
    return {
        "id": c.id,
        "tenant_id": c.tenant_id,
        "name": c.name,
        "credit_code": c.credit_code,
        "short_name": c.short_name,
        "company_type": c.company_type,
        "registered_address": c.registered_address,
        "legal_representative": c.legal_representative,
        "established_date": c.established_date,
        "business_license_url": c.business_license_url,
        "business_scope": c.business_scope,
        "certification_status": c.certification_status,
        "certification_submitted_at": c.certification_submitted_at,
        "certification_approved_at": c.certification_approved_at,
        "certification_expires_at": c.certification_expires_at,
        "invoice_title": c.invoice_title,
        "tax_id": c.tax_id,
        "bank_name": c.bank_name,
        "bank_account": c.bank_account,
        "company_phone": c.company_phone,
        "company_address": c.company_address,
        "industry": c.industry,
        "company_size": c.company_size,
        "registered_capital": c.registered_capital,
        "annual_revenue": c.annual_revenue,
        "tags": c.tags or [],
        "notes": c.notes,
        "status": c.status,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
        "created_by": c.created_by,
        "updated_by": c.updated_by,
    }


# ---------------------------------------------------------------------------
# 业务服务
# ---------------------------------------------------------------------------


class CompanyService:
    """企业主体业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, data: CompanyCreateReq) -> Dict[str, Any]:
        """新建企业。"""
        # 校验信用代码唯一性
        if data.credit_code:
            existing = await self._get_by_credit_code(data.credit_code)
            if existing:
                raise ValueError(f"credit_code '{data.credit_code}' 已存在 (id={existing.id})")

        company = Company(
            tenant_id=data.tenant_id,
            name=data.name,
            credit_code=data.credit_code,
            short_name=data.short_name,
            company_type=data.company_type,
            registered_address=data.registered_address,
            legal_representative=data.legal_representative,
            established_date=data.established_date,
            business_license_url=data.business_license_url,
            business_scope=data.business_scope,
            invoice_title=data.invoice_title,
            tax_id=data.tax_id,
            bank_name=data.bank_name,
            bank_account=data.bank_account,
            company_phone=data.company_phone,
            company_address=data.company_address,
            industry=data.industry,
            company_size=data.company_size,
            registered_capital=data.registered_capital,
            annual_revenue=data.annual_revenue,
            tags=data.tags or [],
            notes=data.notes,
            status="active",
            certification_status="pending",
        )
        self.db.add(company)
        await self.db.commit()
        await self.db.refresh(company)
        logger.info("company created: id=%s name=%s", company.id, company.name)
        return _company_to_dict(company)

    async def get(self, company_id: int) -> Optional[Dict[str, Any]]:
        """获取企业详情。"""
        company = await self.db.get(Company, company_id)
        if not company:
            return None
        return _company_to_dict(company)

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        status: Optional[str] = None,
        certification_status: Optional[str] = None,
        company_type: Optional[str] = None,
        industry: Optional[str] = None,
    ) -> CompanyListResp:
        """企业列表（分页 + 多维筛选 + 搜索）。"""
        conditions = []
        if search:
            like = f"%{search}%"
            conditions.append(
                or_(
                    Company.name.like(like),
                    Company.short_name.like(like),
                    Company.credit_code.like(like),
                    Company.legal_representative.like(like),
                )
            )
        if status:
            conditions.append(Company.status == status)
        if certification_status:
            conditions.append(Company.certification_status == certification_status)
        if company_type:
            conditions.append(Company.company_type == company_type)
        if industry:
            conditions.append(Company.industry == industry)

        # 总数
        count_stmt = select(func.count(Company.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar_one()

        # 列表
        offset = (page - 1) * page_size
        list_stmt = select(Company).order_by(Company.id.desc()).offset(offset).limit(page_size)
        if conditions:
            list_stmt = list_stmt.where(and_(*conditions))
        rows = (await self.db.execute(list_stmt)).scalars().all()

        return CompanyListResp(
            total=total,
            page=page,
            page_size=page_size,
            items=[CompanyResp(**_company_to_dict(c)) for c in rows],
        )

    async def update(self, company_id: int, data: CompanyUpdateReq) -> Optional[Dict[str, Any]]:
        """更新企业。"""
        company = await self.db.get(Company, company_id)
        if not company:
            return None
        updates = data.model_dump(exclude_unset=True)
        # 敏感字段特殊处理：信用代码不通过 update 修改（防破坏唯一性）
        updates.pop("credit_code", None)
        for k, v in updates.items():
            setattr(company, k, v)
        # 认证状态变更时记录时间戳
        if "certification_status" in updates:
            if updates["certification_status"] == "submitted" and not company.certification_submitted_at:
                company.certification_submitted_at = datetime.now(timezone.utc)
            elif updates["certification_status"] == "approved":
                company.certification_approved_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(company)
        return _company_to_dict(company)

    async def archive(self, company_id: int) -> Optional[Dict[str, Any]]:
        """归档企业（软删除：status=archived）。"""
        company = await self.db.get(Company, company_id)
        if not company:
            return None
        company.status = "archived"
        await self.db.commit()
        await self.db.refresh(company)
        return _company_to_dict(company)

    async def search(self, q: str, limit: int = 20) -> List[Dict[str, Any]]:
        """按名称/信用代码搜索（用于自动补全）。"""
        like = f"%{q}%"
        stmt = (
            select(Company)
            .where(or_(Company.name.like(like), Company.credit_code.like(like), Company.short_name.like(like)))
            .order_by(Company.id.desc())
            .limit(limit)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return [_company_to_dict(c) for c in rows]

    async def stats(self) -> CompanyStatsResp:
        """统计概览。"""
        # 按 status
        by_status_stmt = select(Company.status, func.count(Company.id)).group_by(
            Company.status
        )
        by_status_rows = (await self.db.execute(by_status_stmt)).all()
        by_status = {s: cnt for s, cnt in by_status_rows}
        # 按 certification_status
        by_cert_rows = (
            await self.db.execute(
                select(Company.certification_status, func.count(Company.id)).group_by(Company.certification_status)
            )
        ).all()
        by_cert = {s: cnt for s, cnt in by_cert_rows}
        # 按 company_type
        by_type_rows = (
            await self.db.execute(
                select(Company.company_type, func.count(Company.id))
                .where(Company.company_type.isnot(None))
                .group_by(Company.company_type)
            )
        ).all()
        by_type = {t: cnt for t, cnt in by_type_rows}
        # 按 industry
        by_ind_rows = (
            await self.db.execute(
                select(Company.industry, func.count(Company.id))
                .where(Company.industry.isnot(None))
                .group_by(Company.industry)
            )
        ).all()
        by_ind = {i: cnt for i, cnt in by_ind_rows}
        total = sum(by_status.values())
        return CompanyStatsResp(
            total=total,
            active=by_status.get("active", 0),
            inactive=by_status.get("inactive", 0),
            archived=by_status.get("archived", 0),
            by_certification_status=by_cert,
            by_company_type=by_type,
            by_industry=by_ind,
        )

    # ----- 内部辅助 -----

    async def _get_by_credit_code(self, credit_code: str) -> Optional[Company]:
        stmt = select(Company).where(Company.credit_code == credit_code)
        return (await self.db.execute(stmt)).scalar_one_or_none()


__all__ = ["CompanyService"]
