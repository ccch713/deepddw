from __future__ import annotations

"""DDW 客户报备与归属插件业务逻辑层。

关键设计：
- :func:`_auto_mark_expired` —— list/get/conflict 等 read 类操作前，
  用 SQL 批量把 ``status='active' AND expire_at < now()`` 的报备标记为
  ``expired``，避免每次 read 还要再过滤过期数据。模式与
  ddw_receivable 的 ``_auto_mark_overdue`` 一致。

- :func:`_compute_expire_at` —— create 时按 ``claim_date + protection_days`` 计算
  expire_at；调用方不能传入 expire_at，统一由服务端计算（防止误传）。

- :class:`LeadClaimService` —— CRUD + 释放 + 冲突查询 + 统计
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import LeadClaim
from .schemas import (
    LeadClaimConflictResp,
    LeadClaimCreateReq,
    LeadClaimListResp,
    LeadClaimResp,
    LeadClaimStatsResp,
    LeadClaimUpdateReq,
    ReleaseClaimReq,
)

logger = logging.getLogger(__name__)

# 仅 active 状态允许修改
_EDITABLE_STATUSES: frozenset[str] = frozenset({"active"})


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _compute_expire_at(claim_date: datetime, protection_days: int) -> datetime:
    """计算保护期截止时间。"""
    return claim_date + timedelta(days=protection_days)


def _to_naive_utc(dt: datetime) -> datetime:
    """统一为不带时区的 UTC datetime（与 SQLAlchemy DateTime 默认行为一致）。"""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


async def _auto_mark_expired(db: AsyncSession) -> None:
    """批量把 active 且 expire_at<now() 的报备标记为 expired。

    在 read 类操作（list / get / conflict / stats）前调用一次，
    保证返回结果的状态字段是最新的（不用再按 expire_at 过滤）。
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stmt = (
        update(LeadClaim)
        .where(
            LeadClaim.status == "active",
            LeadClaim.expire_at.isnot(None),
            LeadClaim.expire_at < now,
        )
        .values(status="expired")
    )
    await db.execute(stmt)
    await db.commit()


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _claim_to_dict(c: LeadClaim) -> Dict[str, Any]:
    """ORM -> dict。"""
    return {
        "id": c.id,
        "tenant_id": c.tenant_id,
        "partner_id": c.partner_id,
        "company_id": c.company_id,
        "claim_date": c.claim_date,
        "protection_days": c.protection_days,
        "expire_at": c.expire_at,
        "contact_person": c.contact_person,
        "contact_phone": c.contact_phone,
        "opportunity_source": c.opportunity_source,
        "expected_amount": c.expected_amount,
        "follow_up_notes": c.follow_up_notes,
        "last_follow_up_at": c.last_follow_up_at,
        "status": c.status,
        "release_reason": c.release_reason,
        "released_at": c.released_at,
        "notes": c.notes,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
        "created_by": c.created_by,
        "updated_by": c.updated_by,
    }


# ---------------------------------------------------------------------------
# 业务服务
# ---------------------------------------------------------------------------


class LeadClaimService:
    """客户报备与归属业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ----- 创建 -----

    async def create(self, data: LeadClaimCreateReq) -> Dict[str, Any]:
        """新建报备。

        - claim_date 默认 now(UTC)
        - expire_at = claim_date + protection_days（服务端计算，**不**取调用方传入）
        - status 默认 active
        - 业务校验：同一公司同一渠道已存在 active 报备时抛 ValueError（防重复占位）
        """
        # 1. claim_date 默认值
        claim_date = data.claim_date or datetime.now(timezone.utc).replace(tzinfo=None)
        claim_date = _to_naive_utc(claim_date)

        # 2. expire_at 服务端计算
        expire_at = _compute_expire_at(claim_date, data.protection_days)

        # 3. 业务校验：同公司同渠道已有 active 报备时拒绝
        if data.partner_id is not None and data.company_id is not None:
            existing = await self._get_active_by_partner_company(
                data.partner_id, data.company_id
            )
            if existing:
                raise ValueError(
                    f"partner_id={data.partner_id} 对 company_id={data.company_id} "
                    f"已有 active 报备 (id={existing.id})，请先释放后再报备"
                )

        claim = LeadClaim(
            tenant_id=data.tenant_id,
            partner_id=data.partner_id,
            company_id=data.company_id,
            claim_date=claim_date,
            protection_days=data.protection_days,
            expire_at=expire_at,
            contact_person=data.contact_person,
            contact_phone=data.contact_phone,
            opportunity_source=data.opportunity_source,
            expected_amount=data.expected_amount,
            follow_up_notes=data.follow_up_notes,
            last_follow_up_at=None,
            status="active",
            release_reason=None,
            released_at=None,
            notes=data.notes,
            created_by=data.created_by,
            updated_by=data.created_by,
        )
        self.db.add(claim)
        await self.db.commit()
        await self.db.refresh(claim)
        logger.info(
            "lead_claim created: id=%s partner_id=%s company_id=%s expire_at=%s",
            claim.id, claim.partner_id, claim.company_id, claim.expire_at,
        )
        return _claim_to_dict(claim)

    # ----- 详情 -----

    async def get(self, claim_id: int) -> Optional[Dict[str, Any]]:
        """获取报备详情（read 前自动标记过期）。"""
        await _auto_mark_expired(self.db)

        c = await self.db.get(LeadClaim, claim_id)
        if not c:
            return None
        return _claim_to_dict(c)

    # ----- 列表 -----

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        partner_id: Optional[int] = None,
        company_id: Optional[int] = None,
        status: Optional[str] = None,
        expire_before: Optional[datetime] = None,
        expire_after: Optional[datetime] = None,
    ) -> LeadClaimListResp:
        """报备列表（分页 + 多维筛选）。

        操作前先 ``_auto_mark_expired`` 一次，确保 active 状态是最新的。
        """
        await _auto_mark_expired(self.db)

        conditions = []
        if partner_id is not None:
            conditions.append(LeadClaim.partner_id == partner_id)
        if company_id is not None:
            conditions.append(LeadClaim.company_id == company_id)
        if status:
            conditions.append(LeadClaim.status == status)
        if expire_before is not None:
            conditions.append(LeadClaim.expire_at.isnot(None))
            conditions.append(LeadClaim.expire_at <= _to_naive_utc(expire_before))
        if expire_after is not None:
            conditions.append(LeadClaim.expire_at.isnot(None))
            conditions.append(LeadClaim.expire_at >= _to_naive_utc(expire_after))

        # total
        count_stmt = select(func.count(LeadClaim.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar_one()

        # list
        offset = (page - 1) * page_size
        list_stmt = (
            select(LeadClaim)
            .order_by(LeadClaim.claim_date.desc(), LeadClaim.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        if conditions:
            list_stmt = list_stmt.where(and_(*conditions))
        rows = (await self.db.execute(list_stmt)).scalars().all()

        return LeadClaimListResp(
            total=total,
            page=page,
            page_size=page_size,
            items=[LeadClaimResp(**_claim_to_dict(c)) for c in rows],
        )

    # ----- 更新 -----

    async def update(
        self, claim_id: int, data: LeadClaimUpdateReq
    ) -> Optional[Dict[str, Any]]:
        """更新报备。

        业务规则：
        - 仅 active 状态允许改基本信息（避免破坏已结束的保护期）
        - expire_at / protection_days / claim_date / status / created_* 不允许通过 update 改
        """
        await _auto_mark_expired(self.db)

        c = await self.db.get(LeadClaim, claim_id)
        if not c:
            return None
        if c.status not in _EDITABLE_STATUSES:
            raise ValueError(
                f"当前 status='{c.status}' 不允许修改（仅允许 active）"
            )

        updates = data.model_dump(exclude_unset=True)
        for k, v in updates.items():
            setattr(c, k, v)

        await self.db.commit()
        await self.db.refresh(c)
        logger.info("lead_claim updated: id=%s fields=%s", c.id, list(updates.keys()))
        return _claim_to_dict(c)

    # ----- 释放 -----

    async def release(
        self, claim_id: int, data: ReleaseClaimReq
    ) -> Optional[Dict[str, Any]]:
        """主动释放报备（status=released）。

        业务规则：
        - 仅 active / expired 状态允许释放（won/lost/released 终态拒绝）
        - 记录 release_reason（可选）和 released_at
        """
        await _auto_mark_expired(self.db)

        c = await self.db.get(LeadClaim, claim_id)
        if not c:
            return None
        if c.status not in ("active", "expired"):
            raise ValueError(
                f"当前 status='{c.status}' 不允许释放（仅允许 active/expired）"
            )

        c.status = "released"
        c.release_reason = data.release_reason
        c.released_at = datetime.now(timezone.utc).replace(tzinfo=None)
        if data.updated_by is not None:
            c.updated_by = data.updated_by

        await self.db.commit()
        await self.db.refresh(c)
        logger.info(
            "lead_claim released: id=%s reason=%s", c.id, data.release_reason
        )
        return _claim_to_dict(c)

    # ----- 冲突查询 -----

    async def conflict(self, company_id: int) -> LeadClaimConflictResp:
        """冲突查询：返回该企业所有报备（含全状态）+ active 计数。

        read 前自动标记过期。
        """
        await _auto_mark_expired(self.db)

        # 全部报备
        all_stmt = (
            select(LeadClaim)
            .where(LeadClaim.company_id == company_id)
            .order_by(LeadClaim.claim_date.desc(), LeadClaim.id.desc())
        )
        rows = (await self.db.execute(all_stmt)).scalars().all()
        items = [LeadClaimResp(**_claim_to_dict(c)) for c in rows]

        # active 计数
        active_count = sum(1 for x in items if x.status == "active")

        return LeadClaimConflictResp(
            company_id=company_id,
            total=len(items),
            active_count=active_count,
            items=items,
        )

    # ----- 统计 -----

    async def stats(self) -> LeadClaimStatsResp:
        """统计概览。

        - 各状态计数（total/active/expired/won/lost/released）
        - 按 partner 分组（仅统计 status=active 的报备，NULL partner 归到 'unknown'）

        read 前自动标记过期。
        """
        await _auto_mark_expired(self.db)

        # 按 status 分组
        by_status_rows = (
            await self.db.execute(
                select(LeadClaim.status, func.count(LeadClaim.id)).group_by(
                    LeadClaim.status
                )
            )
        ).all()
        by_status: Dict[str, int] = {s: c for s, c in by_status_rows}

        # 按 partner 分组（仅 active 报备）
        by_partner_rows = (
            await self.db.execute(
                select(LeadClaim.partner_id, func.count(LeadClaim.id))
                .where(LeadClaim.status == "active")
                .group_by(LeadClaim.partner_id)
            )
        ).all()
        by_partner: Dict[str, int] = {}
        for pid, cnt in by_partner_rows:
            if pid is None:
                by_partner["unknown"] = cnt
            else:
                by_partner[str(pid)] = cnt

        return LeadClaimStatsResp(
            total=sum(by_status.values()),
            active=by_status.get("active", 0),
            expired=by_status.get("expired", 0),
            won=by_status.get("won", 0),
            lost=by_status.get("lost", 0),
            released=by_status.get("released", 0),
            by_partner=by_partner,
        )

    # ----- 内部辅助 -----

    async def _get_active_by_partner_company(
        self, partner_id: int, company_id: int
    ) -> Optional[LeadClaim]:
        """查询同 partner + company 的 active 报备（用于唯一性校验）。"""
        stmt = select(LeadClaim).where(
            and_(
                LeadClaim.partner_id == partner_id,
                LeadClaim.company_id == company_id,
                LeadClaim.status == "active",
            )
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()


__all__ = [
    "LeadClaimService",
    "_auto_mark_expired",
    "_compute_expire_at",
    "_to_naive_utc",
]
