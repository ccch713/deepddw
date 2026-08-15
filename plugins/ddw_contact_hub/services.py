from __future__ import annotations

"""DDW 联系人管理插件业务逻辑层。"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Contact
from .schemas import (
    ContactCreateReq,
    ContactListResp,
    ContactResp,
    ContactStatsResp,
    ContactUpdateReq,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _contact_to_dict(c: Contact) -> Dict[str, Any]:
    """ORM → dict（用于响应）。"""
    return {
        "id": c.id,
        "tenant_id": c.tenant_id,
        "company_id": c.company_id,
        "name": c.name,
        "phone": c.phone,
        "email": c.email,
        "position": c.position,
        "department": c.department,
        "wechat": c.wechat,
        "tags": c.tags or [],
        "groups": c.groups or [],
        "is_primary": c.is_primary,
        "notes": c.notes,
        "status": c.status,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
        "created_by": c.created_by,
    }


# ---------------------------------------------------------------------------
# 业务服务
# ---------------------------------------------------------------------------


class ContactService:
    """联系人业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, data: ContactCreateReq) -> Dict[str, Any]:
        """新建联系人。"""
        contact = Contact(
            tenant_id=data.tenant_id,
            company_id=data.company_id,
            name=data.name,
            phone=data.phone,
            email=data.email,
            position=data.position,
            department=data.department,
            wechat=data.wechat,
            tags=data.tags or [],
            groups=data.groups or [],
            is_primary=data.is_primary,
            notes=data.notes,
            status="active",
        )
        self.db.add(contact)
        await self.db.commit()
        await self.db.refresh(contact)
        logger.info(
            "contact created: id=%s name=%s company_id=%s",
            contact.id,
            contact.name,
            contact.company_id,
        )
        return _contact_to_dict(contact)

    async def get(self, contact_id: int) -> Optional[Dict[str, Any]]:
        """获取联系人详情。"""
        contact = await self.db.get(Contact, contact_id)
        if not contact:
            return None
        return _contact_to_dict(contact)

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        status: Optional[str] = None,
        company_id: Optional[int] = None,
        is_primary: Optional[bool] = None,
        tag: Optional[str] = None,
        group: Optional[str] = None,
    ) -> ContactListResp:
        """联系人列表（分页 + 多维筛选 + 搜索）。"""
        conditions = []
        if search:
            like = f"%{search}%"
            conditions.append(
                or_(
                    Contact.name.like(like),
                    Contact.phone.like(like),
                    Contact.email.like(like),
                    Contact.position.like(like),
                    Contact.department.like(like),
                )
            )
        if status:
            conditions.append(Contact.status == status)
        if company_id is not None:
            conditions.append(Contact.company_id == company_id)
        if is_primary is not None:
            conditions.append(Contact.is_primary == is_primary)
        if tag:
            # JSON 列表里包含 tag：SQLite/PostgreSQL 通用做法用 JSON 文本包含
            conditions.append(Contact.tags.contains(f'"{tag}"'))
        if group:
            conditions.append(Contact.groups.contains(f'"{group}"'))

        # 总数
        count_stmt = select(func.count(Contact.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar_one()

        # 列表
        offset = (page - 1) * page_size
        list_stmt = (
            select(Contact).order_by(Contact.id.desc()).offset(offset).limit(page_size)
        )
        if conditions:
            list_stmt = list_stmt.where(and_(*conditions))
        rows = (await self.db.execute(list_stmt)).scalars().all()

        return ContactListResp(
            total=total,
            page=page,
            page_size=page_size,
            items=[ContactResp(**_contact_to_dict(c)) for c in rows],
        )

    async def list_by_company(self, company_id: int) -> List[Dict[str, Any]]:
        """某企业所有联系人（按 is_primary 优先 + id 倒序）。"""
        stmt = (
            select(Contact)
            .where(Contact.company_id == company_id)
            .order_by(Contact.is_primary.desc(), Contact.id.desc())
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return [_contact_to_dict(c) for c in rows]

    async def update(
        self, contact_id: int, data: ContactUpdateReq
    ) -> Optional[Dict[str, Any]]:
        """更新联系人。"""
        contact = await self.db.get(Contact, contact_id)
        if not contact:
            return None
        updates = data.model_dump(exclude_unset=True)
        for k, v in updates.items():
            setattr(contact, k, v)
        await self.db.commit()
        await self.db.refresh(contact)
        return _contact_to_dict(contact)

    async def delete(self, contact_id: int) -> bool:
        """硬删除联系人（任务规范明确 DELETE 走真删除）。

        联系人无重要业务依赖，删除后无审计要求，直接物理删除。
        """
        contact = await self.db.get(Contact, contact_id)
        if not contact:
            return False
        await self.db.delete(contact)
        await self.db.commit()
        logger.info("contact hard-deleted: id=%s", contact_id)
        return True

    async def search(self, q: str, limit: int = 20) -> List[Dict[str, Any]]:
        """按姓名/手机/邮箱搜索（用于自动补全）。"""
        like = f"%{q}%"
        stmt = (
            select(Contact)
            .where(
                or_(
                    Contact.name.like(like),
                    Contact.phone.like(like),
                    Contact.email.like(like),
                )
            )
            .order_by(Contact.is_primary.desc(), Contact.id.desc())
            .limit(limit)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return [_contact_to_dict(c) for c in rows]

    async def stats(self) -> ContactStatsResp:
        """统计概览：total/status 分布 + 主联系人数 + 独立联系人数 + by_company。"""
        # 按 status
        by_status_rows = (
            await self.db.execute(
                select(Contact.status, func.count(Contact.id)).group_by(Contact.status)
            )
        ).all()
        by_status = {s: cnt for s, cnt in by_status_rows}
        # 主联系人数
        primary = (
            await self.db.execute(
                select(func.count(Contact.id)).where(Contact.is_primary.is_(True))
            )
        ).scalar_one()
        # 有关联企业的联系人数
        with_company = (
            await self.db.execute(
                select(func.count(Contact.id)).where(Contact.company_id.isnot(None))
            )
        ).scalar_one()
        # 独立联系人数
        independent = (
            await self.db.execute(
                select(func.count(Contact.id)).where(Contact.company_id.is_(None))
            )
        ).scalar_one()
        # 按 company_id 分组（仅统计有 company_id 的）
        by_company_rows = (
            await self.db.execute(
                select(Contact.company_id, func.count(Contact.id))
                .where(Contact.company_id.isnot(None))
                .group_by(Contact.company_id)
            )
        ).all()
        by_company = {str(cid): cnt for cid, cnt in by_company_rows}
        total = sum(by_status.values())

        return ContactStatsResp(
            total=total,
            active=by_status.get("active", 0),
            inactive=by_status.get("inactive", 0),
            archived=by_status.get("archived", 0),
            primary=primary,
            with_company=with_company,
            independent=independent,
            by_company=by_company,
        )


__all__ = ["ContactService"]
