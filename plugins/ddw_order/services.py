from __future__ import annotations

"""DDW 订单管理插件业务逻辑层。

关键函数：
- :func:`generate_order_no` —— 按 ORD-YYYYMMDD-NNN 规则生成单号
- :func:`compute_total_amount` —— 按 items 累加总金额
- :func:`validate_transition` —— 状态机合法性校验

服务：
- :class:`OrderService` —— 订单 CRUD + 状态机 + 统计
"""

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Order
from .schemas import (
    OrderCancelReq,
    OrderCreateReq,
    OrderItemReq,
    OrderListResp,
    OrderResp,
    OrderStatsResp,
    OrderUpdateReq,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 辅助函数：单号生成
# ---------------------------------------------------------------------------


async def generate_order_no(db: AsyncSession) -> str:
    """生成当日唯一单号：ORD-YYYYMMDD-NNN（NNN 从 001 开始递增）。

    通过 ``like 'ORD-YYYYMMDD-%'`` 查出当日所有单号，解析末段序号取最大值 + 1。
    极小概率碰撞：理论上同毫秒并发插入可能拿到相同序号，
    数据库 unique 约束兜底（重复时由调用方在 ``IntegrityError`` 中重试）。
    """
    today_str = date.today().strftime("%Y%m%d")
    prefix = f"ORD-{today_str}-"
    stmt = select(Order.order_no).where(Order.order_no.like(f"{prefix}%"))
    rows = (await db.execute(stmt)).scalars().all()
    max_seq = 0
    for no in rows:
        try:
            seq = int(no.rsplit("-", 1)[-1])
            if seq > max_seq:
                max_seq = seq
        except (ValueError, IndexError):
            continue
    return f"{prefix}{max_seq + 1:03d}"


# ---------------------------------------------------------------------------
# 辅助函数：金额计算
# ---------------------------------------------------------------------------

ZERO = Decimal("0")


def compute_total_amount(items: Sequence[OrderItemReq]) -> Decimal:
    """按 items 累加总金额（item.amount 缺省时 quantity × unit_price）。

    返回：``Decimal("0.00")`` 量化后的总金额。
    """
    total = ZERO
    for it in items:
        if it.amount is not None:
            line = it.amount
        elif it.unit_price is not None:
            line = (it.unit_price * Decimal(it.quantity)).quantize(Decimal("0.01"))
        else:
            line = ZERO
        total += line
    return total.quantize(Decimal("0.01"))


def _serialize_item(it: OrderItemReq) -> Dict[str, Any]:
    """OrderItemReq -> JSON-friendly dict（Decimal 走 str 避免精度丢失）。"""
    return {
        "product_name": it.product_name,
        "quantity": it.quantity,
        "unit_price": str(it.unit_price) if it.unit_price is not None else None,
        "amount": str(it.amount) if it.amount is not None else None,
    }


# ---------------------------------------------------------------------------
# 状态机
# ---------------------------------------------------------------------------

# 合法迁移表
ALLOWED_TRANSITIONS: Dict[str, set] = {
    "pending": {"confirmed", "cancelled"},
    "confirmed": {"delivered", "cancelled"},
    "delivered": {"completed"},
    "completed": set(),  # 终态
    "cancelled": set(),  # 终态
}


def validate_transition(current: str, target: str) -> None:
    """校验状态迁移合法性，非法时抛 :class:`ValueError`。

    - ``current`` / ``target`` 必须是已知状态；
    - ``target`` 必须在 ``current`` 的允许迁移集中。
    """
    if current not in ALLOWED_TRANSITIONS:
        raise ValueError(f"未知订单当前状态：{current!r}")
    if target not in ALLOWED_TRANSITIONS[current]:
        allowed = sorted(ALLOWED_TRANSITIONS[current])
        allowed_repr = allowed if allowed else "（无，终态）"
        raise ValueError(
            f"订单状态 '{current}' 不允许迁移到 '{target}'（允许的下一态：{allowed_repr}）"
        )


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _order_to_dict(o: Order) -> Dict[str, Any]:
    """Order ORM -> dict（items 直接用 DB 返回的 JSON list）。"""
    return {
        "id": o.id,
        "tenant_id": o.tenant_id,
        "company_id": o.company_id,
        "contract_id": o.contract_id,
        "order_no": o.order_no,
        "title": o.title,
        "total_amount": o.total_amount,
        "items": list(o.items) if o.items is not None else [],
        "status": o.status,
        "confirmed_at": o.confirmed_at,
        "delivered_at": o.delivered_at,
        "completed_at": o.completed_at,
        "cancelled_at": o.cancelled_at,
        "cancel_reason": o.cancel_reason,
        "notes": o.notes,
        "created_at": o.created_at,
        "updated_at": o.updated_at,
        "created_by": o.created_by,
    }


def _now_naive_utc() -> datetime:
    """返回 naive UTC（与 SQLAlchemy DateTime 列一致）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# 业务服务
# ---------------------------------------------------------------------------


class OrderService:
    """订单业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # create
    # ------------------------------------------------------------------ #

    async def create(self, data: OrderCreateReq) -> Dict[str, Any]:
        """新建订单（status=pending）。

        - 自动生成 order_no（ORD-YYYYMMDD-NNN）
        - 按 items 自动计算 total_amount
        - items 以 JSON list 持久化（Decimal -> str）
        """
        total = compute_total_amount(data.items)
        order_no = await generate_order_no(self.db)

        order = Order(
            tenant_id=data.tenant_id,
            company_id=data.company_id,
            contract_id=data.contract_id,
            order_no=order_no,
            title=data.title,
            total_amount=total,
            items=[_serialize_item(it) for it in data.items],
            status="pending",
            notes=data.notes,
            created_by=data.created_by,
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)

        logger.info(
            "order created: id=%s no=%s total=%s items=%d",
            order.id,
            order.order_no,
            total,
            len(data.items),
        )
        return _order_to_dict(order)

    # ------------------------------------------------------------------ #
    # get / list
    # ------------------------------------------------------------------ #

    async def get(self, order_id: int) -> Optional[Dict[str, Any]]:
        """获取订单详情（含 items）。"""
        order = await self.db.get(Order, order_id)
        if not order:
            return None
        return _order_to_dict(order)

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        status: Optional[str] = None,
        company_id: Optional[int] = None,
        contract_id: Optional[int] = None,
    ) -> OrderListResp:
        """订单列表（分页 + 多维筛选 + 模糊搜索）。

        - 搜索：order_no / title（LIKE）
        - 精确筛选：status / company_id / contract_id
        """
        conditions = []
        if search:
            like = f"%{search}%"
            conditions.append(
                or_(
                    Order.order_no.like(like),
                    Order.title.like(like),
                )
            )
        if status:
            conditions.append(Order.status == status)
        if company_id is not None:
            conditions.append(Order.company_id == company_id)
        if contract_id is not None:
            conditions.append(Order.contract_id == contract_id)

        # total
        count_stmt = select(func.count(Order.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar_one()

        # items
        offset = (page - 1) * page_size
        list_stmt = (
            select(Order)
            .order_by(Order.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        if conditions:
            list_stmt = list_stmt.where(and_(*conditions))
        rows = (await self.db.execute(list_stmt)).scalars().all()

        return OrderListResp(
            total=total,
            page=page,
            page_size=page_size,
            items=[OrderResp(**_order_to_dict(o)) for o in rows],
        )

    # ------------------------------------------------------------------ #
    # update（仅 pending）
    # ------------------------------------------------------------------ #

    async def update(self, order_id: int, data: OrderUpdateReq) -> Optional[Dict[str, Any]]:
        """更新订单。

        - 字段级更新（model_dump(exclude_unset=True)）
        - 若 ``items`` 字段在请求中：整体替换（传 [] 则清空并置 total=0；
          传非空则重算 total_amount）
        - 限制：**仅 pending 状态可改**（confirmed / delivered / completed /
          cancelled 抛 ValueError）
        """
        order = await self.db.get(Order, order_id)
        if not order:
            return None
        if order.status != "pending":
            raise ValueError(
                f"仅 pending 状态的订单可编辑；当前状态 '{order.status}' 不可修改"
            )

        updates = data.model_dump(exclude_unset=True)
        items_payload_raw: Optional[List[Dict[str, Any]]] = updates.pop("items", None)
        items_changed = "items" in data.model_fields_set and data.items is not None

        # 字段级更新
        for k, v in updates.items():
            setattr(order, k, v)

        # items 整体替换 + 重算总金额
        if items_changed:
            if items_payload_raw:
                item_reqs = [OrderItemReq(**it) for it in items_payload_raw]
                order.items = [_serialize_item(it) for it in item_reqs]
                order.total_amount = compute_total_amount(item_reqs)
            else:
                order.items = []
                order.total_amount = ZERO

        await self.db.commit()
        await self.db.refresh(order)
        logger.info(
            "order updated: id=%s items_changed=%s", order.id, items_changed
        )
        return _order_to_dict(order)

    # ------------------------------------------------------------------ #
    # 取消（DELETE）
    # ------------------------------------------------------------------ #

    async def cancel(self, order_id: int, req: OrderCancelReq) -> Optional[Dict[str, Any]]:
        """取消订单（pending / confirmed → cancelled）。

        - ``cancelled_at`` 设为 now
        - ``cancel_reason`` 写入原因
        - 其他状态抛 ValueError
        - 不存在返回 None
        """
        order = await self.db.get(Order, order_id)
        if not order:
            return None
        # 通过 validate_transition 复用统一状态机校验
        validate_transition(order.status, "cancelled")
        now = _now_naive_utc()
        order.status = "cancelled"
        order.cancelled_at = now
        order.cancel_reason = req.reason
        await self.db.commit()
        await self.db.refresh(order)
        logger.info(
            "order cancelled: id=%s reason=%r", order.id, req.reason
        )
        return _order_to_dict(order)

    # ------------------------------------------------------------------ #
    # 状态机正向流转
    # ------------------------------------------------------------------ #

    async def confirm(self, order_id: int) -> Optional[Dict[str, Any]]:
        """确认订单（pending → confirmed，confirmed_at = now）。"""
        return await self._transition(order_id, "confirmed", set_confirmed_at=True)

    async def deliver(self, order_id: int) -> Optional[Dict[str, Any]]:
        """交付订单（confirmed → delivered，delivered_at = now）。"""
        return await self._transition(order_id, "delivered", set_delivered_at=True)

    async def complete(self, order_id: int) -> Optional[Dict[str, Any]]:
        """完成订单（delivered → completed，completed_at = now）。"""
        return await self._transition(order_id, "completed", set_completed_at=True)

    async def _transition(
        self,
        order_id: int,
        target: str,
        *,
        set_confirmed_at: bool = False,
        set_delivered_at: bool = False,
        set_completed_at: bool = False,
    ) -> Optional[Dict[str, Any]]:
        order = await self.db.get(Order, order_id)
        if not order:
            return None
        validate_transition(order.status, target)
        now = _now_naive_utc()
        order.status = target
        if set_confirmed_at:
            order.confirmed_at = now
        elif set_delivered_at:
            order.delivered_at = now
        elif set_completed_at:
            order.completed_at = now
        await self.db.commit()
        await self.db.refresh(order)
        logger.info(
            "order %s -> %s: id=%s", order.status, target, order.id
        )
        return _order_to_dict(order)

    # ------------------------------------------------------------------ #
    # stats
    # ------------------------------------------------------------------ #

    async def stats(self) -> OrderStatsResp:
        """统计概览：各状态计数 + 总金额 + 已完成金额。"""
        by_status_rows = (
            await self.db.execute(
                select(Order.status, func.count(Order.id)).group_by(Order.status)
            )
        ).all()
        by_status: Dict[str, int] = {s: cnt for s, cnt in by_status_rows}

        # 总金额（所有 total_amount 之和）
        total_amount = (
            await self.db.execute(
                select(func.coalesce(func.sum(Order.total_amount), ZERO))
            )
        ).scalar_one()

        # 已完成金额
        completed_amount = (
            await self.db.execute(
                select(func.coalesce(func.sum(Order.total_amount), ZERO)).where(
                    Order.status == "completed"
                )
            )
        ).scalar_one()

        return OrderStatsResp(
            total=sum(by_status.values()),
            pending=by_status.get("pending", 0),
            confirmed=by_status.get("confirmed", 0),
            delivered=by_status.get("delivered", 0),
            completed=by_status.get("completed", 0),
            cancelled=by_status.get("cancelled", 0),
            total_amount=Decimal(total_amount) if total_amount is not None else ZERO,
            completed_amount=Decimal(completed_amount) if completed_amount is not None else ZERO,
        )


__all__ = [
    "ALLOWED_TRANSITIONS",
    "OrderService",
    "compute_total_amount",
    "generate_order_no",
    "validate_transition",
]
