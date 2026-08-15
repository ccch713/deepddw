from __future__ import annotations

"""DDW 账号/租户/实例映射插件业务逻辑层。"""

import builtins
import logging
from typing import Any, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AccountLink
from .schemas import (
    AccountLinkCreateReq,
    AccountLinkListResp,
    AccountLinkResp,
    AccountLinkStatsResp,
    AccountLinkUpdateReq,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _account_link_to_dict(al: AccountLink) -> dict[str, Any]:
    """ORM → dict（用于响应）。"""
    return {
        "id": al.id,
        "tenant_id": al.tenant_id,
        "company_id": al.company_id,
        "link_type": al.link_type,
        "external_id": al.external_id,
        "external_name": al.external_name,
        "metadata_json": dict(al.metadata_json) if al.metadata_json else {},
        "status": al.status,
        "created_at": al.created_at,
        "updated_at": al.updated_at,
        "created_by": al.created_by,
    }


# ---------------------------------------------------------------------------
# 业务服务
# ---------------------------------------------------------------------------


class AccountLinkService:
    """账号/租户/实例映射业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # create
    # ------------------------------------------------------------------ #

    async def create(self, data: AccountLinkCreateReq) -> dict[str, Any]:
        """新建账号链接。"""
        # 校验同 (tenant_id, link_type) 内 external_id 唯一
        existing = await self._get_by_link_type_and_extid(
            tenant_id=data.tenant_id, link_type=data.link_type, external_id=data.external_id
        )
        if existing:
            raise ValueError(
                f"({data.link_type}, '{data.external_id}') 已存在 (id={existing.id})"
            )

        link = AccountLink(
            tenant_id=data.tenant_id,
            company_id=data.company_id,
            link_type=data.link_type,
            external_id=data.external_id,
            external_name=data.external_name,
            metadata_json=data.metadata_json or {},
            status="active",
            created_by=data.created_by,
        )
        self.db.add(link)
        await self.db.commit()
        await self.db.refresh(link)
        logger.info(
            "account_link created: id=%s type=%s ext_id=%s company_id=%s",
            link.id,
            link.link_type,
            link.external_id,
            link.company_id,
        )
        return _account_link_to_dict(link)

    # ------------------------------------------------------------------ #
    # get
    # ------------------------------------------------------------------ #

    async def get(self, link_id: int) -> dict[str, Any] | None:
        """获取账号链接详情。"""
        link = await self.db.get(AccountLink, link_id)
        if not link:
            return None
        return _account_link_to_dict(link)

    # ------------------------------------------------------------------ #
    # list（分页 + 多维筛选）
    # ------------------------------------------------------------------ #

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        company_id: Optional[int] = None,
        link_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> AccountLinkListResp:
        """账号链接列表（分页 + 多维筛选）。"""
        conditions = []
        if company_id is not None:
            conditions.append(AccountLink.company_id == company_id)
        if link_type:
            conditions.append(AccountLink.link_type == link_type)
        if status:
            conditions.append(AccountLink.status == status)

        # total
        count_stmt = select(func.count(AccountLink.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar_one()

        # items
        offset = (page - 1) * page_size
        list_stmt = (
            select(AccountLink)
            .order_by(AccountLink.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        if conditions:
            list_stmt = list_stmt.where(and_(*conditions))
        rows = (await self.db.execute(list_stmt)).scalars().all()

        return AccountLinkListResp(
            total=total,
            page=page,
            page_size=page_size,
            items=[AccountLinkResp(**_account_link_to_dict(a)) for a in rows],
        )

    # ------------------------------------------------------------------ #
    # get_by_company
    # ------------------------------------------------------------------ #

    async def get_by_company(self, company_id: int) -> builtins.list[dict[str, Any]]:
        """获取某企业的所有账号链接（不区分状态）。"""
        stmt = (
            select(AccountLink)
            .where(AccountLink.company_id == company_id)
            .order_by(AccountLink.id.desc())
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return [_account_link_to_dict(a) for a in rows]

    # ------------------------------------------------------------------ #
    # update
    # ------------------------------------------------------------------ #

    async def update(self, link_id: int, data: AccountLinkUpdateReq) -> dict[str, Any] | None:
        """更新账号链接。"""
        link = await self.db.get(AccountLink, link_id)
        if not link:
            return None
        updates = data.model_dump(exclude_unset=True)
        for k, v in updates.items():
            setattr(link, k, v)
        await self.db.commit()
        await self.db.refresh(link)
        logger.info("account_link updated: id=%s", link.id)
        return _account_link_to_dict(link)

    # ------------------------------------------------------------------ #
    # deactivate（软删除：status=inactive）
    # ------------------------------------------------------------------ #

    async def deactivate(self, link_id: int) -> dict[str, Any] | None:
        """停用账号链接（软删除：status=inactive）。"""
        link = await self.db.get(AccountLink, link_id)
        if not link:
            return None
        link.status = "inactive"
        await self.db.commit()
        await self.db.refresh(link)
        logger.info("account_link deactivated: id=%s", link.id)
        return _account_link_to_dict(link)

    # ------------------------------------------------------------------ #
    # stats
    # ------------------------------------------------------------------ #

    async def stats(self) -> AccountLinkStatsResp:
        """统计概览。"""
        # 按 status
        by_status_rows = (
            await self.db.execute(
                select(AccountLink.status, func.count(AccountLink.id)).group_by(
                    AccountLink.status
                )
            )
        ).all()
        by_status = {s: cnt for s, cnt in by_status_rows}

        # 按 link_type
        by_type_rows = (
            await self.db.execute(
                select(AccountLink.link_type, func.count(AccountLink.id)).group_by(
                    AccountLink.link_type
                )
            )
        ).all()
        by_type = {t: cnt for t, cnt in by_type_rows}

        total = sum(by_status.values())
        return AccountLinkStatsResp(
            total=total,
            active=by_status.get("active", 0),
            inactive=by_status.get("inactive", 0),
            by_link_type=by_type,
        )

    # ----- 内部辅助 -----

    async def _get_by_link_type_and_extid(
        self, tenant_id: int, link_type: str, external_id: str
    ) -> AccountLink | None:
        """按 (tenant_id, link_type, external_id) 查询。"""
        stmt = select(AccountLink).where(
            and_(
                AccountLink.tenant_id == tenant_id,
                AccountLink.link_type == link_type,
                AccountLink.external_id == external_id,
            )
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()


__all__ = ["AccountLinkService"]
