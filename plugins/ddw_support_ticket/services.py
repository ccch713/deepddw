from __future__ import annotations

"""DDW 售后工单插件业务逻辑层。

关键设计：
- ``ALLOWED_TRANSITIONS`` 模块级常量定义所有合法状态迁移。
- :func:`validate_transition` —— 校验状态迁移，非法抛 ``ValueError``。
- :func:`generate_ticket_no` —— 按 TKT-YYYYMMDD-NNN 规则生成单号。
- :class:`SupportTicketService` —— 工单 CRUD + 状态机 + 统计。
"""

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import SupportTicket
from .schemas import (
    CATEGORIES,
    PRIORITIES,
    STATUSES,
    TicketAssignReq,
    TicketCreateReq,
    TicketListResp,
    TicketResolveReq,
    TicketResp,
    TicketStatsResp,
    TicketUpdateReq,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 状态机
# ---------------------------------------------------------------------------
#
# 合法迁移路径：
#   open         → in_progress
#   in_progress  → resolved
#   resolved     → closed
#
# 设计要点：
# - 严格线性推进，不可跳（与 contract_core 风格一致）。
# - 终止态 closed 不在任何 from 集合中。
# - ALLOWED_TRANSITIONS 是单一事实来源（single source of truth）。
# ---------------------------------------------------------------------------

ALLOWED_TRANSITIONS: Dict[str, set] = {
    "open": {"in_progress"},
    "in_progress": {"resolved"},
    "resolved": {"closed"},
    "closed": set(),  # 终止态
}


def validate_transition(current: str, target: str) -> None:
    """校验状态迁移是否合法，非法抛 ``ValueError``。

    校验规则：
    - target 必须在 ALLOWED_TRANSITIONS 字典中存在（即是合法状态）。
    - current → target 必须在 ALLOWED_TRANSITIONS[current] 集合内。
    """
    if target not in ALLOWED_TRANSITIONS:
        raise ValueError(
            f"invalid target status '{target}'，合法值: {STATUSES}"
        )
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ValueError(
            f"invalid transition: {current} -> {target} "
            f"（仅允许: {sorted(allowed) if allowed else '（无）'}）"
        )


# ---------------------------------------------------------------------------
# 辅助函数：单号生成
# ---------------------------------------------------------------------------


async def generate_ticket_no(db: AsyncSession) -> str:
    """生成当日唯一工单号：TKT-YYYYMMDD-NNN（NNN 从 001 开始递增）。

    通过 ``like 'TKT-YYYYMMDD-%'`` 查出当日所有工单号，解析末段序号取最大值 + 1。
    极小概率碰撞：理论上同毫秒并发插入可能拿到相同序号，
    数据库 unique 约束兜底（重复时由调用方在 ``IntegrityError`` 中重试）。
    """
    today_str = date.today().strftime("%Y%m%d")
    prefix = f"TKT-{today_str}-"
    stmt = select(SupportTicket.ticket_no).where(
        SupportTicket.ticket_no.like(f"{prefix}%")
    )
    rows = (await db.execute(stmt)).scalars().all()
    max_seq = 0
    for no in rows:
        try:
            seq = int(no.rsplit("-", 1)[-1])
            max_seq = max(max_seq, seq)
        except (ValueError, IndexError):
            continue
    return f"{prefix}{max_seq + 1:03d}"


# ---------------------------------------------------------------------------
# 辅助：naive UTC（SQLite 不存时区）
# ---------------------------------------------------------------------------


def _now_naive_utc() -> datetime:
    """返回 naive UTC datetime（SQLite 不支持时区，统一存 naive）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _validate_category(category: str) -> None:
    """校验 category 合法性。"""
    if category not in CATEGORIES:
        raise ValueError(
            f"invalid category '{category}'，合法值: {CATEGORIES}"
        )


def _validate_priority(priority: str) -> None:
    """校验 priority 合法性。"""
    if priority not in PRIORITIES:
        raise ValueError(
            f"invalid priority '{priority}'，合法值: {PRIORITIES}"
        )


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _ticket_to_dict(t: SupportTicket) -> Dict[str, Any]:
    """ORM → dict（用于响应）。"""
    return {
        "id": t.id,
        "tenant_id": t.tenant_id,
        "company_id": t.company_id,
        "instance_id": t.instance_id,
        "ticket_no": t.ticket_no,
        "title": t.title,
        "category": t.category,
        "priority": t.priority,
        "description": t.description,
        "resolution": t.resolution,
        "assigned_to": t.assigned_to,
        "status": t.status,
        "resolved_at": t.resolved_at,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
        "created_by": t.created_by,
    }


# ---------------------------------------------------------------------------
# 业务服务
# ---------------------------------------------------------------------------


class SupportTicketService:
    """售后工单业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # create
    # ------------------------------------------------------------------ #

    async def create(self, data: TicketCreateReq) -> Dict[str, Any]:
        """新建工单。

        - 自动生成 ticket_no（TKT-YYYYMMDD-NNN）
        - 状态默认为 open
        - 校验 category / priority 合法性
        """
        _validate_category(data.category)
        _validate_priority(data.priority)

        ticket_no = await generate_ticket_no(self.db)
        ticket = SupportTicket(
            tenant_id=data.tenant_id,
            company_id=data.company_id,
            instance_id=data.instance_id,
            ticket_no=ticket_no,
            title=data.title,
            category=data.category,
            priority=data.priority,
            description=data.description,
            assigned_to=data.assigned_to,
            status="open",
            created_by=data.created_by,
        )
        self.db.add(ticket)
        await self.db.commit()
        await self.db.refresh(ticket)
        logger.info(
            "ticket created: id=%s no=%s category=%s priority=%s",
            ticket.id,
            ticket.ticket_no,
            ticket.category,
            ticket.priority,
        )
        return _ticket_to_dict(ticket)

    # ------------------------------------------------------------------ #
    # get / list
    # ------------------------------------------------------------------ #

    async def get(self, ticket_id: int) -> Optional[Dict[str, Any]]:
        """获取工单详情。"""
        ticket = await self.db.get(SupportTicket, ticket_id)
        if not ticket:
            return None
        return _ticket_to_dict(ticket)

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        company_id: Optional[int] = None,
        instance_id: Optional[int] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        assigned_to: Optional[int] = None,
        status: Optional[str] = None,
    ) -> TicketListResp:
        """工单列表（分页 + 多维筛选）。

        筛选维度：company / instance / category / priority / assigned_to / status。
        """
        conditions = []
        if company_id is not None:
            conditions.append(SupportTicket.company_id == company_id)
        if instance_id is not None:
            conditions.append(SupportTicket.instance_id == instance_id)
        if category:
            conditions.append(SupportTicket.category == category)
        if priority:
            conditions.append(SupportTicket.priority == priority)
        if assigned_to is not None:
            conditions.append(SupportTicket.assigned_to == assigned_to)
        if status:
            conditions.append(SupportTicket.status == status)

        # total
        count_stmt = select(func.count(SupportTicket.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar_one()

        # items
        offset = (page - 1) * page_size
        list_stmt = (
            select(SupportTicket)
            .order_by(SupportTicket.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        if conditions:
            list_stmt = list_stmt.where(and_(*conditions))
        rows = (await self.db.execute(list_stmt)).scalars().all()

        return TicketListResp(
            total=total,
            page=page,
            page_size=page_size,
            items=[TicketResp(**_ticket_to_dict(t)) for t in rows],
        )

    # ------------------------------------------------------------------ #
    # update
    # ------------------------------------------------------------------ #

    async def update(
        self, ticket_id: int, data: TicketUpdateReq
    ) -> Optional[Dict[str, Any]]:
        """更新工单（status 不在本请求中，走专门状态机端点）。

        校验 category / priority 合法性（如传入）。
        """
        ticket = await self.db.get(SupportTicket, ticket_id)
        if not ticket:
            return None

        updates = data.model_dump(exclude_unset=True)
        if "category" in updates and updates["category"] is not None:
            _validate_category(updates["category"])
        if "priority" in updates and updates["priority"] is not None:
            _validate_priority(updates["priority"])

        for k, v in updates.items():
            setattr(ticket, k, v)
        await self.db.commit()
        await self.db.refresh(ticket)
        logger.info("ticket updated: id=%s", ticket.id)
        return _ticket_to_dict(ticket)

    # ------------------------------------------------------------------ #
    # 状态机：分配 / 开始 / 解决 / 关闭
    # ------------------------------------------------------------------ #

    async def assign(
        self, ticket_id: int, data: TicketAssignReq
    ) -> Optional[Dict[str, Any]]:
        """分配处理人（任意状态都可改 assigned_to；不影响 status）。

        - 写入 assigned_to
        - 不触发状态机迁移
        """
        ticket = await self.db.get(SupportTicket, ticket_id)
        if not ticket:
            return None
        ticket.assigned_to = data.assigned_to
        await self.db.commit()
        await self.db.refresh(ticket)
        logger.info(
            "ticket assigned: id=%s assigned_to=%s", ticket.id, ticket.assigned_to
        )
        return _ticket_to_dict(ticket)

    async def start(self, ticket_id: int) -> Optional[Dict[str, Any]]:
        """开始处理（open → in_progress）。"""
        return await self._transition(ticket_id, "in_progress")

    async def resolve(
        self, ticket_id: int, data: TicketResolveReq
    ) -> Optional[Dict[str, Any]]:
        """解决工单（in_progress → resolved, resolution 必填, resolved_at=now）。"""
        return await self._transition(
            ticket_id,
            "resolved",
            timestamp_field="resolved_at",
            extra_fields={"resolution": data.resolution},
        )

    async def close(self, ticket_id: int) -> Optional[Dict[str, Any]]:
        """关闭工单（resolved → closed）。"""
        return await self._transition(ticket_id, "closed")

    async def _transition(
        self,
        ticket_id: int,
        target: str,
        timestamp_field: Optional[str] = None,
        extra_fields: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """统一状态机迁移实现。

        - 校验 current → target 合法（非法抛 ValueError）
        - 写入目标状态
        - 写入对应时间戳字段（如 resolved_at）
        - 写入额外审计字段（如 resolution）
        """
        ticket = await self.db.get(SupportTicket, ticket_id)
        if not ticket:
            return None
        validate_transition(ticket.status, target)
        ticket.status = target
        if timestamp_field:
            setattr(ticket, timestamp_field, _now_naive_utc())
        if extra_fields:
            for k, v in extra_fields.items():
                setattr(ticket, k, v)
        await self.db.commit()
        await self.db.refresh(ticket)
        logger.info(
            "ticket %s -> %s: id=%s", ticket.status, target, ticket.id
        )
        return _ticket_to_dict(ticket)

    # ------------------------------------------------------------------ #
    # stats
    # ------------------------------------------------------------------ #

    async def stats(self) -> TicketStatsResp:
        """统计概览：各状态计数 + 按 category / priority 分组。"""
        # by_status
        by_status_rows = (
            await self.db.execute(
                select(SupportTicket.status, func.count(SupportTicket.id)).group_by(
                    SupportTicket.status
                )
            )
        ).all()
        by_status: Dict[str, int] = dict(by_status_rows)

        # by_category
        by_category_rows = (
            await self.db.execute(
                select(SupportTicket.category, func.count(SupportTicket.id)).group_by(
                    SupportTicket.category
                )
            )
        ).all()
        by_category: Dict[str, int] = dict(by_category_rows)

        # by_priority
        by_priority_rows = (
            await self.db.execute(
                select(SupportTicket.priority, func.count(SupportTicket.id)).group_by(
                    SupportTicket.priority
                )
            )
        ).all()
        by_priority: Dict[str, int] = dict(by_priority_rows)

        return TicketStatsResp(
            total=sum(by_status.values()),
            open=by_status.get("open", 0),
            in_progress=by_status.get("in_progress", 0),
            resolved=by_status.get("resolved", 0),
            closed=by_status.get("closed", 0),
            by_category=by_category,
            by_priority=by_priority,
        )


__all__ = [
    "ALLOWED_TRANSITIONS",
    "SupportTicketService",
    "generate_ticket_no",
    "validate_transition",
]
