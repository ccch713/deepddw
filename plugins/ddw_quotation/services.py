from __future__ import annotations

"""DDW 报价单管理插件业务逻辑层。

关键函数：
- :func:`generate_quotation_no` —— 按 QT-YYYYMMDD-NNN 规则生成单号
- :func:`compute_amounts` —— 计算总金额与折后金额

服务：
- :class:`QuotationService` —— 报价单 CRUD + 状态机 + 统计
"""

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Quotation, QuotationItem
from .schemas import (
    QuotationCreateReq,
    QuotationItemReq,
    QuotationListResp,
    QuotationResp,
    QuotationStatsResp,
    QuotationUpdateReq,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 辅助函数：单号生成
# ---------------------------------------------------------------------------


async def generate_quotation_no(db: AsyncSession) -> str:
    """生成当日唯一单号：QT-YYYYMMDD-NNN（NNN 从 001 开始递增）。

    通过 ``like 'QT-YYYYMMDD-%'`` 查出当日所有单号，解析末段序号取最大值 + 1。
    极小概率碰撞：理论上同毫秒并发插入可能拿到相同序号，
    数据库 unique 约束兜底（重复时由调用方在 ``IntegrityError`` 中重试）。
    """
    today_str = date.today().strftime("%Y%m%d")
    prefix = f"QT-{today_str}-"
    stmt = select(Quotation.quotation_no).where(Quotation.quotation_no.like(f"{prefix}%"))
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
ONE_HUNDRED = Decimal("100")


def compute_amounts(
    items: Sequence[QuotationItemReq],
    discount_rate: Optional[Decimal] = None,
) -> Tuple[Decimal, Decimal, List[Dict[str, Any]]]:
    """计算明细行金额、总金额、折后金额。

    规则：
    - 行金额 amount：未传时按 ``quantity * unit_price`` 计算
    - 总金额 total_amount = sum(item.amount)
    - 折后金额 final_amount = total * discount_rate / 100

    返回：``(total_amount, final_amount, normalized_items)``
    其中 ``normalized_items`` 是补全了 amount 字段的 dict 列表（供持久化）。
    """
    rate = discount_rate if discount_rate is not None else ONE_HUNDRED

    normalized: List[Dict[str, Any]] = []
    total = ZERO
    for it in items:
        # 行金额：未传或为 None 时按 quantity * unit_price 算
        if it.amount is not None:
            line_amount = it.amount
        elif it.unit_price is not None:
            line_amount = (it.unit_price * Decimal(it.quantity)).quantize(Decimal("0.01"))
        else:
            line_amount = ZERO
        total += line_amount
        normalized.append(
            {
                "product_name": it.product_name,
                "product_type": it.product_type,
                "product_code": it.product_code,
                "quantity": it.quantity,
                "unit": it.unit,
                "unit_price": it.unit_price,
                "amount": line_amount,
                "description": it.description,
                "sort_order": it.sort_order,
            }
        )

    # 折后金额：total * rate / 100
    final = (total * rate / ONE_HUNDRED).quantize(Decimal("0.01"))
    total = total.quantize(Decimal("0.01"))
    return total, final, normalized


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _item_to_dict(i: QuotationItem) -> Dict[str, Any]:
    """QuotationItem ORM → dict。"""
    return {
        "id": i.id,
        "quotation_id": i.quotation_id,
        "product_name": i.product_name,
        "product_type": i.product_type,
        "product_code": i.product_code,
        "quantity": i.quantity,
        "unit": i.unit,
        "unit_price": i.unit_price,
        "amount": i.amount,
        "description": i.description,
        "sort_order": i.sort_order,
        "created_at": i.created_at,
    }


def _quotation_to_dict(q: Quotation, items: Optional[List[QuotationItem]] = None) -> Dict[str, Any]:
    """Quotation ORM → dict（items 可选）。"""
    if items is None:
        items = list(getattr(q, "items_relation", []) or [])
    return {
        "id": q.id,
        "tenant_id": q.tenant_id,
        "company_id": q.company_id,
        "contact_id": q.contact_id,
        "opportunity_id": q.opportunity_id,
        "quotation_no": q.quotation_no,
        "title": q.title,
        "total_amount": q.total_amount,
        "discount_rate": q.discount_rate,
        "final_amount": q.final_amount,
        "currency": q.currency,
        "valid_until": q.valid_until,
        "terms": q.terms,
        "notes": q.notes,
        "status": q.status,
        "sent_at": q.sent_at,
        "accepted_at": q.accepted_at,
        "rejected_at": q.rejected_at,
        "created_at": q.created_at,
        "updated_at": q.updated_at,
        "created_by": q.created_by,
        "items": [_item_to_dict(i) for i in items],
    }


# ---------------------------------------------------------------------------
# 业务服务
# ---------------------------------------------------------------------------


# 状态机合法迁移
_ALLOWED_TRANSITIONS: Dict[str, set] = {
    "draft": {"sent", "rejected"},  # 草稿可直接拒绝（内部撤销）
    "sent": {"accepted", "rejected", "expired"},
    "accepted": set(),
    "rejected": set(),
    "expired": set(),
}


class QuotationService:
    """报价单业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # 内部：拉取明细
    # ------------------------------------------------------------------ #

    async def _load_items(self, quotation_id: int) -> List[QuotationItem]:
        """按 sort_order 升序、同序时按 id 升序，加载明细列表。"""
        stmt = (
            select(QuotationItem)
            .where(QuotationItem.quotation_id == quotation_id)
            .order_by(QuotationItem.sort_order.asc(), QuotationItem.id.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    # ------------------------------------------------------------------ #
    # create
    # ------------------------------------------------------------------ #

    async def create(self, data: QuotationCreateReq) -> Dict[str, Any]:
        """新建报价单。

        - 自动生成 quotation_no（QT-YYYYMMDD-NNN）
        - 根据 items 自动计算 total_amount / final_amount
        - 状态默认为 draft
        """
        if not data.items:
            raise ValueError("报价单至少需要 1 条明细")

        total, final, normalized = compute_amounts(data.items, data.discount_rate)
        quotation_no = await generate_quotation_no(self.db)

        quotation = Quotation(
            tenant_id=data.tenant_id,
            company_id=data.company_id,
            contact_id=data.contact_id,
            opportunity_id=data.opportunity_id,
            quotation_no=quotation_no,
            title=data.title,
            total_amount=total,
            discount_rate=data.discount_rate if data.discount_rate is not None else ONE_HUNDRED,
            final_amount=final,
            currency=data.currency,
            valid_until=data.valid_until,
            terms=data.terms,
            notes=data.notes,
            status="draft",
            created_by=data.created_by,
        )
        self.db.add(quotation)
        await self.db.flush()  # 拿到 quotation.id

        # 批量插入明细
        item_objs = [QuotationItem(quotation_id=quotation.id, **row) for row in normalized]
        if item_objs:
            self.db.add_all(item_objs)

        await self.db.commit()
        await self.db.refresh(quotation)

        items = await self._load_items(quotation.id)
        logger.info(
            "quotation created: id=%s no=%s total=%s final=%s items=%d",
            quotation.id,
            quotation.quotation_no,
            total,
            final,
            len(items),
        )
        return _quotation_to_dict(quotation, items)

    # ------------------------------------------------------------------ #
    # get / list
    # ------------------------------------------------------------------ #

    async def get(self, quotation_id: int) -> Optional[Dict[str, Any]]:
        """获取报价单详情（含 items）。"""
        quotation = await self.db.get(Quotation, quotation_id)
        if not quotation:
            return None
        items = await self._load_items(quotation.id)
        return _quotation_to_dict(quotation, items)

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        status: Optional[str] = None,
        company_id: Optional[int] = None,
    ) -> QuotationListResp:
        """报价单列表（分页 + 筛选 + 搜索）。

        搜索字段：quotation_no / title。
        列表不展开 items（性能考虑）；详情请用 ``get()``。
        """
        conditions = []
        if search:
            like = f"%{search}%"
            conditions.append(
                or_(
                    Quotation.quotation_no.like(like),
                    Quotation.title.like(like),
                )
            )
        if status:
            conditions.append(Quotation.status == status)
        if company_id is not None:
            conditions.append(Quotation.company_id == company_id)

        # total
        count_stmt = select(func.count(Quotation.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar_one()

        # items
        offset = (page - 1) * page_size
        list_stmt = (
            select(Quotation)
            .order_by(Quotation.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        if conditions:
            list_stmt = list_stmt.where(and_(*conditions))
        rows = (await self.db.execute(list_stmt)).scalars().all()

        return QuotationListResp(
            total=total,
            page=page,
            page_size=page_size,
            items=[QuotationResp(**_quotation_to_dict(q, items=[])) for q in rows],
        )

    # ------------------------------------------------------------------ #
    # update
    # ------------------------------------------------------------------ #

    async def update(self, quotation_id: int, data: QuotationUpdateReq) -> Optional[Dict[str, Any]]:
        """更新报价单。

        - 字段级更新（model_dump(exclude_unset=True)）
        - 若 ``data.items`` 非 None：级联删除旧明细，插入新明细
        - 若 ``data.items`` 为 None：保留现有明细
        - 若 ``data.items`` 为 []：清空明细
        - 重新计算 total_amount / final_amount（如有 items / discount_rate 变更）
        """
        quotation = await self.db.get(Quotation, quotation_id)
        if not quotation:
            return None

        updates = data.model_dump(exclude_unset=True)
        items_payload_raw: Optional[List[Dict[str, Any]]] = updates.pop("items", None)
        # 把 dict 重新包装为 QuotationItemReq（compute_amounts 依赖 Pydantic 字段访问）
        items_payload: Optional[List[QuotationItemReq]] = (
            [QuotationItemReq(**it) for it in items_payload_raw] if items_payload_raw is not None else None
        )
        items_changed = "items" in data.model_fields_set and data.items is not None

        # 字段级更新
        for k, v in updates.items():
            setattr(quotation, k, v)

        # 明细级联重建
        if items_changed:
            # 删旧
            old_items_stmt = select(QuotationItem).where(QuotationItem.quotation_id == quotation.id)
            for old in (await self.db.execute(old_items_stmt)).scalars().all():
                await self.db.delete(old)
            await self.db.flush()
            # 插新
            if items_payload:
                total, final, normalized = compute_amounts(items_payload, quotation.discount_rate)
                quotation.total_amount = total
                quotation.final_amount = final
                new_items = [QuotationItem(quotation_id=quotation.id, **row) for row in normalized]
                self.db.add_all(new_items)
            else:
                quotation.total_amount = ZERO
                quotation.final_amount = ZERO

        # 若只改了 discount_rate（无 items 变更），重算 final_amount
        if not items_changed and "discount_rate" in updates:
            assert quotation.total_amount is not None
            new_final = (
                quotation.total_amount * quotation.discount_rate / ONE_HUNDRED
            ).quantize(Decimal("0.01"))
            quotation.final_amount = new_final

        await self.db.commit()
        await self.db.refresh(quotation)
        items = await self._load_items(quotation.id)
        logger.info("quotation updated: id=%s items_changed=%s", quotation.id, items_changed)
        return _quotation_to_dict(quotation, items)

    # ------------------------------------------------------------------ #
    # delete（硬删除，DB cascade 清明细）
    # ------------------------------------------------------------------ #

    async def delete(self, quotation_id: int) -> bool:
        """硬删除报价单（FK ON DELETE CASCADE 自动清理 items）。"""
        quotation = await self.db.get(Quotation, quotation_id)
        if not quotation:
            return False
        await self.db.delete(quotation)
        await self.db.commit()
        logger.info("quotation hard-deleted: id=%s", quotation_id)
        return True

    # ------------------------------------------------------------------ #
    # 状态机
    # ------------------------------------------------------------------ #

    async def mark_sent(self, quotation_id: int) -> Optional[Dict[str, Any]]:
        """标记为已发送（draft → sent）。"""
        return await self._transition(quotation_id, "sent", require_from={"draft"})

    async def mark_accepted(self, quotation_id: int) -> Optional[Dict[str, Any]]:
        """标记为已接受（sent → accepted）。"""
        return await self._transition(quotation_id, "accepted", require_from={"sent"})

    async def mark_rejected(self, quotation_id: int) -> Optional[Dict[str, Any]]:
        """标记为已拒绝（draft/sent → rejected）。"""
        return await self._transition(quotation_id, "rejected", require_from={"draft", "sent"})

    async def _transition(
        self,
        quotation_id: int,
        target: str,
        require_from: set,
    ) -> Optional[Dict[str, Any]]:
        quotation = await self.db.get(Quotation, quotation_id)
        if not quotation:
            return None
        if quotation.status not in require_from:
            allowed = sorted(require_from)
            raise ValueError(
                f"报价单当前状态 '{quotation.status}' 不允许迁移到 '{target}' "
                f"（仅允许来源状态：{allowed}）"
            )
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        quotation.status = target
        if target == "sent":
            quotation.sent_at = now
        elif target == "accepted":
            quotation.accepted_at = now
        elif target == "rejected":
            quotation.rejected_at = now
        await self.db.commit()
        await self.db.refresh(quotation)
        items = await self._load_items(quotation.id)
        logger.info(
            "quotation %s -> %s: id=%s", quotation.status, target, quotation.id
        )
        return _quotation_to_dict(quotation, items)

    # ------------------------------------------------------------------ #
    # stats
    # ------------------------------------------------------------------ #

    async def stats(self) -> QuotationStatsResp:
        """统计概览：各状态计数 + 总金额 / 已接受金额。"""
        # 状态分组
        by_status_rows = (
            await self.db.execute(
                select(Quotation.status, func.count(Quotation.id)).group_by(Quotation.status)
            )
        ).all()
        by_status: Dict[str, int] = {s: cnt for s, cnt in by_status_rows}

        # 总金额（所有 final_amount 之和）
        total_amount = (
            await self.db.execute(
                select(func.coalesce(func.sum(Quotation.final_amount), ZERO))
            )
        ).scalar_one()

        # 已接受金额
        accepted_amount = (
            await self.db.execute(
                select(func.coalesce(func.sum(Quotation.final_amount), ZERO)).where(
                    Quotation.status == "accepted"
                )
            )
        ).scalar_one()

        return QuotationStatsResp(
            total=sum(by_status.values()),
            draft=by_status.get("draft", 0),
            sent=by_status.get("sent", 0),
            accepted=by_status.get("accepted", 0),
            rejected=by_status.get("rejected", 0),
            expired=by_status.get("expired", 0),
            total_amount=Decimal(total_amount) if total_amount is not None else ZERO,
            accepted_amount=Decimal(accepted_amount) if accepted_amount is not None else ZERO,
        )


__all__ = [
    "QuotationService",
    "compute_amounts",
    "generate_quotation_no",
]
