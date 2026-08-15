from __future__ import annotations

"""DDW Token 额度管理插件业务逻辑层。

关键设计：
- :func:`_entitlement_to_dict` —— ORM → dict（含 remaining_tokens 派生字段）
- :class:`TokenEntitlementService` —— CRUD + 消耗 + 统计

业务规则：
- create：必填 entitlement_type；api_key_masked 必须含 ``****``（拒绝明文）
- update：不能改 used_tokens（仅 consume 端点能改）
- consume(id, tokens)：
    * 若 ``overage_allowed=False`` 且 ``used_tokens + tokens > allocated_tokens``：
      抛 ``ValueError``（拒绝超量）
    * 若允许超量：正常累加 used_tokens
    * 响应字段 overage 负数表示超量，0 表示恰好用完，正数表示还有余
- delete：硬删除（本表无 status 字段）
- stats：total_allocated / total_used / total_remaining + by_type + 超量企业数
"""

import logging
from typing import Any, Optional

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import TokenEntitlement
from .schemas import (
    TokenConsumeReq,
    TokenConsumeResp,
    TokenEntitlementCreateReq,
    TokenEntitlementListResp,
    TokenEntitlementResp,
    TokenEntitlementStatsResp,
    TokenEntitlementUpdateReq,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _entitlement_to_dict(e: TokenEntitlement) -> dict[str, Any]:
    """ORM -> dict（用于响应；包含 remaining_tokens 派生字段）。"""
    return {
        "id": e.id,
        "tenant_id": e.tenant_id,
        "company_id": e.company_id,
        "instance_id": e.instance_id,
        "entitlement_type": e.entitlement_type,
        "allocated_tokens": e.allocated_tokens,
        "used_tokens": e.used_tokens,
        "remaining_tokens": e.allocated_tokens - e.used_tokens,
        "overage_allowed": e.overage_allowed,
        "api_key_masked": e.api_key_masked,
        "llm_endpoint": e.llm_endpoint,
        "notes": e.notes,
        "created_at": e.created_at,
        "updated_at": e.updated_at,
        "created_by": e.created_by,
    }


# ---------------------------------------------------------------------------
# 业务服务
# ---------------------------------------------------------------------------


class TokenEntitlementService:
    """Token 额度分配业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ----- CRUD -----

    async def create(self, data: TokenEntitlementCreateReq) -> dict[str, Any]:
        """新建额度分配。

        - used_tokens 默认 0
        - api_key_masked 已在校验层保证是脱敏形式
        """
        ent = TokenEntitlement(
            tenant_id=data.tenant_id,
            company_id=data.company_id,
            instance_id=data.instance_id,
            entitlement_type=data.entitlement_type,
            allocated_tokens=data.allocated_tokens,
            used_tokens=0,
            overage_allowed=data.overage_allowed,
            api_key_masked=data.api_key_masked,
            llm_endpoint=data.llm_endpoint,
            notes=data.notes,
            created_by=data.created_by,
        )
        self.db.add(ent)
        await self.db.commit()
        await self.db.refresh(ent)
        logger.info(
            "token entitlement created: id=%s type=%s allocated=%s",
            ent.id, ent.entitlement_type, ent.allocated_tokens,
        )
        return _entitlement_to_dict(ent)

    async def get(self, ent_id: int) -> Optional[dict[str, Any]]:
        """获取额度分配详情。"""
        ent = await self.db.get(TokenEntitlement, ent_id)
        if not ent:
            return None
        return _entitlement_to_dict(ent)

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        company_id: Optional[int] = None,
        instance_id: Optional[int] = None,
        entitlement_type: Optional[str] = None,
    ) -> TokenEntitlementListResp:
        """额度分配列表（分页 + 多维筛选）。

        筛选：
        - company_id：按关联企业
        - instance_id：按关联实例
        - entitlement_type：按类型（platform / custom-key / local-llm）
        """
        conditions = []
        if company_id is not None:
            conditions.append(TokenEntitlement.company_id == company_id)
        if instance_id is not None:
            conditions.append(TokenEntitlement.instance_id == instance_id)
        if entitlement_type:
            conditions.append(TokenEntitlement.entitlement_type == entitlement_type)

        # total
        count_stmt = select(func.count(TokenEntitlement.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar_one()

        # items
        offset = (page - 1) * page_size
        list_stmt = (
            select(TokenEntitlement)
            .order_by(TokenEntitlement.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        if conditions:
            list_stmt = list_stmt.where(and_(*conditions))
        rows = (await self.db.execute(list_stmt)).scalars().all()

        return TokenEntitlementListResp(
            total=total,
            page=page,
            page_size=page_size,
            items=[TokenEntitlementResp(**_entitlement_to_dict(e)) for e in rows],
        )

    async def update(
        self, ent_id: int, data: TokenEntitlementUpdateReq
    ) -> Optional[dict[str, Any]]:
        """更新额度分配（不能改 used_tokens / tenant_id）。

        - 字段级更新（model_dump(exclude_unset=True)）
        - used_tokens 显式剔除（仅 consume 端点能改）
        - tenant_id 显式剔除（保持租户隔离）
        """
        ent = await self.db.get(TokenEntitlement, ent_id)
        if not ent:
            return None

        updates = data.model_dump(exclude_unset=True)
        # 保护字段：使用量 / 租户 ID 不能通过 update 改
        updates.pop("used_tokens", None)
        updates.pop("tenant_id", None)

        for k, v in updates.items():
            setattr(ent, k, v)

        await self.db.commit()
        await self.db.refresh(ent)
        logger.info(
            "token entitlement updated: id=%s fields=%s", ent.id, list(updates.keys())
        )
        return _entitlement_to_dict(ent)

    async def delete(self, ent_id: int) -> bool:
        """硬删除额度分配（本表无 status 字段，删除即物理删）。"""
        ent = await self.db.get(TokenEntitlement, ent_id)
        if not ent:
            return False
        await self.db.delete(ent)
        await self.db.commit()
        logger.info("token entitlement hard-deleted: id=%s", ent_id)
        return True

    # ----- 消耗 -----

    async def consume(
        self, ent_id: int, data: TokenConsumeReq
    ) -> Optional[dict[str, Any]]:
        """消耗 tokens（核心业务逻辑）。

        业务规则：
        1. 若 ``overage_allowed=False`` 且 ``used_tokens + tokens > allocated_tokens``：
           抛 ``ValueError``（拒绝超量），原 used_tokens 不变
        2. 若允许超量：正常累加 used_tokens
        3. 返回：
            - used_tokens / remaining_tokens / overage（负数表示超量）
        """
        ent = await self.db.get(TokenEntitlement, ent_id)
        if not ent:
            return None

        tokens = data.tokens
        new_used = ent.used_tokens + tokens

        if not ent.overage_allowed and new_used > ent.allocated_tokens:
            remaining = ent.allocated_tokens - ent.used_tokens
            raise ValueError(
                f"额度不足：本次需消耗 {tokens} tokens，剩余仅 {remaining} tokens，"
                f"且该分配未开启超量允许 (overage_allowed=False)"
            )

        ent.used_tokens = new_used
        await self.db.commit()
        await self.db.refresh(ent)
        logger.info(
            "token entitlement consumed: id=%s tokens=%s new_used=%s",
            ent.id, tokens, ent.used_tokens,
        )

        resp = TokenConsumeResp(
            id=ent.id,
            tokens_consumed=tokens,
            allocated_tokens=ent.allocated_tokens,
            used_tokens=ent.used_tokens,
            remaining_tokens=ent.allocated_tokens - ent.used_tokens,
            overage=ent.allocated_tokens - ent.used_tokens,
            overage_allowed=ent.overage_allowed,
        )
        return resp.model_dump()

    # ----- 统计 -----

    async def stats(self) -> TokenEntitlementStatsResp:
        """统计概览。

        - total_count：分配记录总数
        - total_allocated / total_used / total_remaining
        - by_type：{type -> {allocated, used, count}}
        - overage_count：已超量的企业数（去重 company_id；company_id 为 NULL 跳过）
        """
        # 总数 + 总分配 + 总使用
        agg = (
            await self.db.execute(
                select(
                    func.count(TokenEntitlement.id).label("cnt"),
                    func.coalesce(func.sum(TokenEntitlement.allocated_tokens), 0).label("alloc"),
                    func.coalesce(func.sum(TokenEntitlement.used_tokens), 0).label("used"),
                )
            )
        ).one()
        agg_map = agg._mapping
        total_count = int(agg_map["cnt"] or 0)
        total_allocated = int(agg_map["alloc"] or 0)
        total_used = int(agg_map["used"] or 0)
        total_remaining = total_allocated - total_used

        # 按 entitlement_type 分组
        by_type_rows = (
            await self.db.execute(
                select(
                    TokenEntitlement.entitlement_type.label("t"),
                    func.count(TokenEntitlement.id).label("cnt"),
                    func.coalesce(func.sum(TokenEntitlement.allocated_tokens), 0).label("alloc"),
                    func.coalesce(func.sum(TokenEntitlement.used_tokens), 0).label("used"),
                ).group_by(TokenEntitlement.entitlement_type)
            )
        ).all()
        by_type: dict[str, dict[str, int]] = {}
        for row in by_type_rows:
            row_map = row._mapping  # SQLAlchemy Row -> dict-like
            by_type[row_map["t"]] = {
                "count": int(row_map["cnt"] or 0),
                "allocated": int(row_map["alloc"] or 0),
                "used": int(row_map["used"] or 0),
            }

        # 超量企业数：used > allocated 且 company_id 不为空的去重数
        overage_case = case(
            (TokenEntitlement.used_tokens > TokenEntitlement.allocated_tokens, 1),
            else_=0,
        )
        overage_rows = (
            await self.db.execute(
                select(
                    func.count(func.distinct(
                        TokenEntitlement.company_id
                    )).label("overage_companies")
                ).where(
                    TokenEntitlement.company_id.isnot(None),
                    overage_case == 1,
                )
            )
        ).one()
        overage_count = int(overage_rows._mapping["overage_companies"] or 0)

        return TokenEntitlementStatsResp(
            total_count=total_count,
            total_allocated=total_allocated,
            total_used=total_used,
            total_remaining=total_remaining,
            by_type=by_type,
            overage_count=overage_count,
        )


__all__ = ["TokenEntitlementService"]
