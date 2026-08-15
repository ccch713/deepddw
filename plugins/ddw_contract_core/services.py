from __future__ import annotations

"""DDW 合同中心插件业务逻辑层。

关键设计：
- ``ALLOWED_TRANSITIONS`` 模块级常量定义所有合法状态迁移。
- :func:`validate_transition` —— 校验状态迁移，非法抛 ``ValueError``。
- :func:`generate_contract_no` —— 按 CT-YYYYMMDD-NNN 规则生成单号。
- :class:`ContractService` —— 合同 CRUD + 状态机 + 统计。
"""

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Contract
from .schemas import (
    ContractCreateReq,
    ContractListResp,
    ContractResp,
    ContractStatsResp,
    ContractUpdateReq,
    RejectReq,
    TerminateReq,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 状态机
# ---------------------------------------------------------------------------
#
# 合法迁移路径：
#   draft            → pending_approval
#   pending_approval → approved | rejected
#   approved         → signed
#   signed           → active | terminated
#   active           → completed | terminated
#   rejected         → draft        (打回重做，可选)
#
# ALLOWED_TRANSITIONS: {from_status: set of allowed to_status}
# 设计要点：
# - 显式列出所有合法迁移，便于审计 / 测试。
# - 终止态 (completed, terminated) 不在任何 from 集合中（除特殊 reject→draft 走法）。
# - "rejected → draft" 作为可选回退（被驳回后允许修改后再次提交）。
# ---------------------------------------------------------------------------

ALLOWED_TRANSITIONS: Dict[str, set] = {
    "draft": {"pending_approval"},
    "pending_approval": {"approved", "rejected"},
    "approved": {"signed"},
    "signed": {"active", "terminated"},
    "active": {"completed", "terminated"},
    "rejected": {"draft"},  # 打回重做
    "completed": set(),  # 终止态
    "terminated": set(),  # 终止态
}

ALL_STATUSES: List[str] = list(ALLOWED_TRANSITIONS.keys())


def validate_transition(current: str, target: str) -> None:
    """校验状态迁移是否合法，非法抛 ``ValueError``。

    校验规则：
    - target 必须在 ALLOWED_TRANSITIONS 字典中存在（即是合法状态）。
    - current → target 必须在 ALLOWED_TRANSITIONS[current] 集合内。
    """
    if target not in ALLOWED_TRANSITIONS:
        raise ValueError(
            f"invalid target status '{target}'，合法值: {ALL_STATUSES}"
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


async def generate_contract_no(db: AsyncSession) -> str:
    """生成当日唯一单号：CT-YYYYMMDD-NNN（NNN 从 001 开始递增）。

    通过 ``like 'CT-YYYYMMDD-%'`` 查出当日所有单号，解析末段序号取最大值 + 1。
    极小概率碰撞：理论上同毫秒并发插入可能拿到相同序号，
    数据库 unique 约束兜底（重复时由调用方在 ``IntegrityError`` 中重试）。
    """
    today_str = date.today().strftime("%Y%m%d")
    prefix = f"CT-{today_str}-"
    stmt = select(Contract.contract_no).where(Contract.contract_no.like(f"{prefix}%"))
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
# 辅助：naive UTC（SQLite 不存时区）
# ---------------------------------------------------------------------------


def _now_naive_utc() -> datetime:
    """返回 naive UTC datetime（SQLite 不支持时区，统一存 naive）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _contract_to_dict(c: Contract) -> Dict[str, Any]:
    """ORM → dict（用于响应）。"""
    return {
        "id": c.id,
        "tenant_id": c.tenant_id,
        "company_id": c.company_id,
        "contact_id": c.contact_id,
        "opportunity_id": c.opportunity_id,
        "quotation_id": c.quotation_id,
        "contract_no": c.contract_no,
        "title": c.title,
        "contract_type": c.contract_type,
        "total_amount": c.total_amount,
        "currency": c.currency,
        "signed_at": c.signed_at,
        "effective_from": c.effective_from,
        "effective_to": c.effective_to,
        "payment_terms": c.payment_terms,
        "deliverables": c.deliverables,
        "sla": c.sla,
        "attachments": c.attachments or [],
        "notes": c.notes,
        "version": c.version,
        "status": c.status,
        "approved_at": c.approved_at,
        "rejected_at": c.rejected_at,
        "reject_reason": c.reject_reason,
        "activated_at": c.activated_at,
        "completed_at": c.completed_at,
        "terminated_at": c.terminated_at,
        "terminate_reason": c.terminate_reason,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
        "created_by": c.created_by,
    }


# ---------------------------------------------------------------------------
# 业务服务
# ---------------------------------------------------------------------------


# 允许修改字段的合同状态（仅草稿 / 驳回后可编辑）
EDITABLE_STATUSES = {"draft", "rejected"}


class ContractService:
    """合同业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # create
    # ------------------------------------------------------------------ #

    async def create(self, data: ContractCreateReq) -> Dict[str, Any]:
        """新建合同。

        - 自动生成 contract_no（CT-YYYYMMDD-NNN）
        - 状态默认为 draft
        - 附件列表默认空 list
        """
        contract_no = await generate_contract_no(self.db)
        contract = Contract(
            tenant_id=data.tenant_id,
            company_id=data.company_id,
            contact_id=data.contact_id,
            opportunity_id=data.opportunity_id,
            quotation_id=data.quotation_id,
            contract_no=contract_no,
            title=data.title,
            contract_type=data.contract_type,
            total_amount=data.total_amount,
            currency=data.currency,
            effective_from=data.effective_from,
            effective_to=data.effective_to,
            payment_terms=data.payment_terms,
            deliverables=data.deliverables,
            sla=data.sla,
            attachments=data.attachments or [],
            notes=data.notes,
            version=1,
            status="draft",
            created_by=data.created_by,
        )
        self.db.add(contract)
        await self.db.commit()
        await self.db.refresh(contract)
        logger.info(
            "contract created: id=%s no=%s type=%s",
            contract.id, contract.contract_no, contract.contract_type,
        )
        return _contract_to_dict(contract)

    # ------------------------------------------------------------------ #
    # get / list
    # ------------------------------------------------------------------ #

    async def get(self, contract_id: int) -> Optional[Dict[str, Any]]:
        """获取合同详情。"""
        contract = await self.db.get(Contract, contract_id)
        if not contract:
            return None
        return _contract_to_dict(contract)

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        status: Optional[str] = None,
        contract_type: Optional[str] = None,
        company_id: Optional[int] = None,
    ) -> ContractListResp:
        """合同列表（分页 + 多维筛选 + 模糊搜索）。

        搜索字段：contract_no / title。
        """
        conditions = []
        if search:
            like = f"%{search}%"
            conditions.append(
                or_(
                    Contract.contract_no.like(like),
                    Contract.title.like(like),
                )
            )
        if status:
            conditions.append(Contract.status == status)
        if contract_type:
            conditions.append(Contract.contract_type == contract_type)
        if company_id is not None:
            conditions.append(Contract.company_id == company_id)

        # total
        count_stmt = select(func.count(Contract.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar_one()

        # items
        offset = (page - 1) * page_size
        list_stmt = (
            select(Contract)
            .order_by(Contract.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        if conditions:
            list_stmt = list_stmt.where(and_(*conditions))
        rows = (await self.db.execute(list_stmt)).scalars().all()

        return ContractListResp(
            total=total,
            page=page,
            page_size=page_size,
            items=[ContractResp(**_contract_to_dict(c)) for c in rows],
        )

    # ------------------------------------------------------------------ #
    # update
    # ------------------------------------------------------------------ #

    async def update(
        self, contract_id: int, data: ContractUpdateReq
    ) -> Optional[Dict[str, Any]]:
        """更新合同。

        业务规则：仅 draft / rejected 状态可修改，其它状态抛 ValueError。
        """
        contract = await self.db.get(Contract, contract_id)
        if not contract:
            return None
        if contract.status not in EDITABLE_STATUSES:
            raise ValueError(
                f"合同当前状态 '{contract.status}' 不允许修改（仅 draft / rejected 可编辑）"
            )

        updates = data.model_dump(exclude_unset=True)
        for k, v in updates.items():
            setattr(contract, k, v)
        await self.db.commit()
        await self.db.refresh(contract)
        logger.info("contract updated: id=%s", contract.id)
        return _contract_to_dict(contract)

    # ------------------------------------------------------------------ #
    # 状态机
    # ------------------------------------------------------------------ #

    async def submit_approval(self, contract_id: int) -> Optional[Dict[str, Any]]:
        """提交审批（draft → pending_approval）。"""
        return await self._transition(contract_id, "pending_approval")

    async def approve(self, contract_id: int) -> Optional[Dict[str, Any]]:
        """审批通过（pending_approval → approved），记录 approved_at。"""
        return await self._transition(
            contract_id, "approved", timestamp_field="approved_at"
        )

    async def reject(
        self, contract_id: int, data: RejectReq
    ) -> Optional[Dict[str, Any]]:
        """审批驳回（pending_approval → rejected, reason 必填），记录 rejected_at。"""
        return await self._transition(
            contract_id,
            "rejected",
            timestamp_field="rejected_at",
            extra_fields={"reject_reason": data.reason},
        )

    async def sign(self, contract_id: int) -> Optional[Dict[str, Any]]:
        """标记已签（approved → signed），记录 signed_at。"""
        return await self._transition(
            contract_id, "signed", timestamp_field="signed_at"
        )

    async def activate(self, contract_id: int) -> Optional[Dict[str, Any]]:
        """激活合同（signed → active），记录 activated_at。"""
        return await self._transition(
            contract_id, "active", timestamp_field="activated_at"
        )

    async def terminate(
        self, contract_id: int, data: TerminateReq
    ) -> Optional[Dict[str, Any]]:
        """终止合同（signed / active → terminated, reason 必填），记录 terminated_at。"""
        return await self._transition(
            contract_id,
            "terminated",
            timestamp_field="terminated_at",
            extra_fields={"terminate_reason": data.reason},
        )

    async def complete(self, contract_id: int) -> Optional[Dict[str, Any]]:
        """完成合同（active → completed），记录 completed_at。"""
        return await self._transition(
            contract_id, "completed", timestamp_field="completed_at"
        )

    async def _transition(
        self,
        contract_id: int,
        target: str,
        timestamp_field: Optional[str] = None,
        extra_fields: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """统一状态机迁移实现。

        - 校验 current → target 合法（非法抛 ValueError）
        - 写入目标状态
        - 写入对应时间戳字段（如 approved_at / signed_at / ...）
        - 写入额外审计字段（如 reject_reason / terminate_reason）
        """
        contract = await self.db.get(Contract, contract_id)
        if not contract:
            return None
        validate_transition(contract.status, target)
        contract.status = target
        if timestamp_field:
            setattr(contract, timestamp_field, _now_naive_utc())
        if extra_fields:
            for k, v in extra_fields.items():
                setattr(contract, k, v)
        await self.db.commit()
        await self.db.refresh(contract)
        logger.info(
            "contract %s -> %s: id=%s", contract.status, target, contract.id
        )
        return _contract_to_dict(contract)

    # ------------------------------------------------------------------ #
    # stats
    # ------------------------------------------------------------------ #

    async def stats(self) -> ContractStatsResp:
        """统计概览：各状态计数 + 按 type/status 分组 + 金额汇总。

        设计：
        - by_status 含所有出现过的状态（保证响应键完整）。
        - 金额汇总用 COALESCE 兜 0，避免 NULL。
        - 即使没有数据也按 ALL_STATUSES 输出 0（但为简洁只输出数据库实际存在的）。
        """
        # by_status
        by_status_rows = (
            await self.db.execute(
                select(Contract.status, func.count(Contract.id)).group_by(
                    Contract.status
                )
            )
        ).all()
        by_status: Dict[str, int] = {s: cnt for s, cnt in by_status_rows}

        # by_type
        by_type_rows = (
            await self.db.execute(
                select(Contract.contract_type, func.count(Contract.id)).group_by(
                    Contract.contract_type
                )
            )
        ).all()
        by_type: Dict[str, int] = {t: cnt for t, cnt in by_type_rows}

        # 金额汇总
        ZERO = Decimal("0")
        total_amount = (
            await self.db.execute(
                select(func.coalesce(func.sum(Contract.total_amount), ZERO))
            )
        ).scalar_one()
        active_amount = (
            await self.db.execute(
                select(func.coalesce(func.sum(Contract.total_amount), ZERO)).where(
                    Contract.status == "active"
                )
            )
        ).scalar_one()
        completed_amount = (
            await self.db.execute(
                select(func.coalesce(func.sum(Contract.total_amount), ZERO)).where(
                    Contract.status == "completed"
                )
            )
        ).scalar_one()

        return ContractStatsResp(
            total=sum(by_status.values()),
            draft=by_status.get("draft", 0),
            pending_approval=by_status.get("pending_approval", 0),
            approved=by_status.get("approved", 0),
            signed=by_status.get("signed", 0),
            active=by_status.get("active", 0),
            completed=by_status.get("completed", 0),
            terminated=by_status.get("terminated", 0),
            rejected=by_status.get("rejected", 0),
            by_type=by_type,
            by_status=by_status,
            total_amount=Decimal(total_amount) if total_amount is not None else ZERO,
            active_amount=Decimal(active_amount) if active_amount is not None else ZERO,
            completed_amount=Decimal(completed_amount) if completed_amount is not None else ZERO,
        )


__all__ = [
    "ALLOWED_TRANSITIONS",
    "ALL_STATUSES",
    "ContractService",
    "EDITABLE_STATUSES",
    "generate_contract_no",
    "validate_transition",
]
