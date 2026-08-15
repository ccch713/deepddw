from __future__ import annotations

"""DDW 商机管理插件业务逻辑层。

关键设计：
- ``STAGES`` 模块级常量定义所有合法阶段及默认 probability。
- ``STAGE_PROBABILITY_MAP`` 与 ``STAGE_LABELS`` 派生自 ``STAGES``，供转换/展示使用。
- ``update_stage`` 与 ``mark_won`` / ``mark_lost`` 会自动同步 probability，避免重复维护。
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Opportunity
from .schemas import (
    MarkLostReq,
    OpportunityCreateReq,
    OpportunityFunnelResp,
    OpportunityListResp,
    OpportunityResp,
    OpportunityStatsResp,
    OpportunityUpdateReq,
    StageFunnelItem,
    StageUpdateReq,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 阶段定义（核心常量）
# ---------------------------------------------------------------------------
#
# 顺序：销售管道从左到右推进，"won" / "lost" 为终止态。
# 三元组：(code, 中文标签, 默认 probability)
#
# 调用方改 stage 时，service 会按本表自动同步 probability，
# 保证两个字段不会脱钩。
# ---------------------------------------------------------------------------

STAGES: List[Tuple[str, str, int]] = [
    ("initial_contact", "初步接触", 10),
    ("demand_confirmation", "需求确认", 20),
    ("proposal_submitted", "方案提交", 40),
    ("quotation_sent", "报价已发", 60),
    ("negotiation", "商务谈判", 75),
    ("contract_pending", "合同待签", 90),
    ("won", "成交", 100),
    ("lost", "丢单", 0),
]

STAGE_PROBABILITY_MAP: Dict[str, int] = {code: prob for code, _label, prob in STAGES}
STAGE_LABELS: Dict[str, str] = {code: label for code, label, _prob in STAGES}
STAGE_CODES: frozenset[str] = frozenset(code for code, _label, _prob in STAGES)

# 用于漏斗/概览统计时保证阶段按管道顺序展示（而不是字母序）
STAGE_DISPLAY_ORDER: List[str] = [code for code, _label, _prob in STAGES]


def get_default_probability(stage: str) -> int:
    """根据阶段返回默认 probability。未知阶段返回 0。"""
    return STAGE_PROBABILITY_MAP.get(stage, 0)


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _opp_to_dict(o: Opportunity) -> Dict[str, Any]:
    """ORM → dict（用于响应）。"""
    return {
        "id": o.id,
        "tenant_id": o.tenant_id,
        "company_id": o.company_id,
        "contact_id": o.contact_id,
        "name": o.name,
        "source": o.source,
        "owner_id": o.owner_id,
        "estimated_amount": o.estimated_amount,
        "stage": o.stage,
        "probability": o.probability,
        "expected_close_date": o.expected_close_date,
        "description": o.description,
        "tags": o.tags or [],
        "status": o.status,
        "won_at": o.won_at,
        "lost_reason": o.lost_reason,
        "created_at": o.created_at,
        "updated_at": o.updated_at,
        "created_by": o.created_by,
    }


# ---------------------------------------------------------------------------
# 业务服务
# ---------------------------------------------------------------------------


class OpportunityService:
    """商机业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ----- CRUD -----

    async def create(self, data: OpportunityCreateReq) -> Dict[str, Any]:
        """新建商机。"""
        # 校验 stage 合法性（未知 stage → ValueError）
        stage = data.stage or "initial_contact"
        if stage not in STAGE_CODES:
            raise ValueError(
                f"非法 stage '{stage}'，合法值: {sorted(STAGE_CODES)}"
            )

        # 如果 caller 没显式给 probability，按 stage 默认值兜底
        prob = data.probability
        if prob is None:
            prob = get_default_probability(stage)

        opp = Opportunity(
            tenant_id=data.tenant_id,
            company_id=data.company_id,
            contact_id=data.contact_id,
            name=data.name,
            source=data.source,
            owner_id=data.owner_id,
            estimated_amount=data.estimated_amount,
            stage=stage,
            probability=prob,
            expected_close_date=data.expected_close_date,
            description=data.description,
            tags=data.tags or [],
            status="open",
            created_by=data.created_by,
        )
        self.db.add(opp)
        await self.db.commit()
        await self.db.refresh(opp)
        logger.info("opportunity created: id=%s name=%s stage=%s", opp.id, opp.name, opp.stage)
        return _opp_to_dict(opp)

    async def get(self, opp_id: int) -> Optional[Dict[str, Any]]:
        """获取商机详情。"""
        opp = await self.db.get(Opportunity, opp_id)
        if not opp:
            return None
        return _opp_to_dict(opp)

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        owner_id: Optional[int] = None,
        stage: Optional[str] = None,
        status: Optional[str] = None,
        company_id: Optional[int] = None,
    ) -> OpportunityListResp:
        """商机列表（分页 + 多维筛选 + 模糊搜索）。"""
        conditions = []
        if search:
            like = f"%{search}%"
            conditions.append(Opportunity.name.like(like))
        if owner_id is not None:
            conditions.append(Opportunity.owner_id == owner_id)
        if stage:
            conditions.append(Opportunity.stage == stage)
        if status:
            conditions.append(Opportunity.status == status)
        if company_id is not None:
            conditions.append(Opportunity.company_id == company_id)

        # 总数
        count_stmt = select(func.count(Opportunity.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar_one()

        # 列表
        offset = (page - 1) * page_size
        list_stmt = (
            select(Opportunity)
            .order_by(Opportunity.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        if conditions:
            list_stmt = list_stmt.where(and_(*conditions))
        rows = (await self.db.execute(list_stmt)).scalars().all()

        return OpportunityListResp(
            total=total,
            page=page,
            page_size=page_size,
            items=[OpportunityResp(**_opp_to_dict(o)) for o in rows],
        )

    async def update(
        self, opp_id: int, data: OpportunityUpdateReq
    ) -> Optional[Dict[str, Any]]:
        """更新商机。"""
        opp = await self.db.get(Opportunity, opp_id)
        if not opp:
            return None
        updates = data.model_dump(exclude_unset=True)
        for k, v in updates.items():
            setattr(opp, k, v)
        await self.db.commit()
        await self.db.refresh(opp)
        return _opp_to_dict(opp)

    async def close(self, opp_id: int) -> Optional[Dict[str, Any]]:
        """关闭商机（status=closed）。"""
        opp = await self.db.get(Opportunity, opp_id)
        if not opp:
            return None
        opp.status = "closed"
        await self.db.commit()
        await self.db.refresh(opp)
        return _opp_to_dict(opp)

    # ----- 阶段流转（核心） -----

    async def update_stage(
        self, opp_id: int, data: StageUpdateReq
    ) -> Optional[Dict[str, Any]]:
        """更新阶段（自动同步 probability）。

        业务规则：
        - stage 必须在 STAGES 合法值内，否则 ValueError
        - probability 会按 STAGE_PROBABILITY_MAP 自动重写为默认值
          （caller 不能用此接口覆盖 probability）
        """
        if data.stage not in STAGE_CODES:
            raise ValueError(
                f"非法 stage '{data.stage}'，合法值: {sorted(STAGE_CODES)}"
            )

        opp = await self.db.get(Opportunity, opp_id)
        if not opp:
            return None

        opp.stage = data.stage
        opp.probability = get_default_probability(data.stage)
        await self.db.commit()
        await self.db.refresh(opp)
        logger.info(
            "opportunity stage updated: id=%s stage=%s probability=%s",
            opp.id, opp.stage, opp.probability,
        )
        return _opp_to_dict(opp)

    async def mark_won(self, opp_id: int) -> Optional[Dict[str, Any]]:
        """标记成交。"""
        opp = await self.db.get(Opportunity, opp_id)
        if not opp:
            return None
        opp.status = "won"
        opp.stage = "won"
        opp.probability = 100
        opp.won_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(opp)
        logger.info("opportunity won: id=%s amount=%s", opp.id, opp.estimated_amount)
        return _opp_to_dict(opp)

    async def mark_lost(
        self, opp_id: int, data: MarkLostReq
    ) -> Optional[Dict[str, Any]]:
        """标记丢单（lost_reason 必填，由 Pydantic 强制）。"""
        opp = await self.db.get(Opportunity, opp_id)
        if not opp:
            return None
        opp.status = "lost"
        opp.stage = "lost"
        opp.probability = 0
        opp.lost_reason = data.lost_reason
        await self.db.commit()
        await self.db.refresh(opp)
        logger.info("opportunity lost: id=%s reason=%s", opp.id, data.lost_reason)
        return _opp_to_dict(opp)

    # ----- 统计 -----

    async def funnel(self) -> OpportunityFunnelResp:
        """漏斗统计：按 stage 分组，含 count + total_amount。

        严格按 STAGE_DISPLAY_ORDER 输出（管道从左到右），
        即使某阶段数据为 0 也保留（count=0, amount=0）。
        """
        # 一次 GROUP BY 拉所有阶段统计
        stmt = (
            select(
                Opportunity.stage,
                func.count(Opportunity.id).label("cnt"),
                func.coalesce(func.sum(Opportunity.estimated_amount), 0).label("amt"),
            )
            .where(Opportunity.status == "open")  # 只统计进行中的
            .group_by(Opportunity.stage)
        )
        rows = (await self.db.execute(stmt)).all()
        by_stage: Dict[str, Tuple[int, Decimal]] = {
            stage: (cnt, Decimal(amt)) for stage, cnt, amt in rows
        }

        items: List[StageFunnelItem] = []
        total = 0
        total_amount = Decimal("0")
        for stage in STAGE_DISPLAY_ORDER:
            cnt, amt = by_stage.get(stage, (0, Decimal("0")))
            items.append(StageFunnelItem(stage=stage, count=cnt, total_amount=amt))
            total += cnt
            total_amount += amt
        return OpportunityFunnelResp(
            stages=items, total=total, total_amount=total_amount
        )

    async def stats(self) -> OpportunityStatsResp:
        """统计概览。"""
        # by_status
        by_status_rows = (
            await self.db.execute(
                select(Opportunity.status, func.count(Opportunity.id)).group_by(
                    Opportunity.status
                )
            )
        ).all()
        by_status: Dict[str, int] = {s: c for s, c in by_status_rows}

        # by_stage（含已成交/丢单的全量统计）
        by_stage_rows = (
            await self.db.execute(
                select(Opportunity.stage, func.count(Opportunity.id)).group_by(
                    Opportunity.stage
                )
            )
        ).all()
        by_stage: Dict[str, int] = {s: c for s, c in by_stage_rows}

        # by_source
        by_source_rows = (
            await self.db.execute(
                select(Opportunity.source, func.count(Opportunity.id))
                .where(Opportunity.source.isnot(None))
                .group_by(Opportunity.source)
            )
        ).all()
        by_source: Dict[str, int] = {s: c for s, c in by_source_rows}

        # 总金额 / 成交金额
        total_amount = (
            await self.db.execute(
                select(func.coalesce(func.sum(Opportunity.estimated_amount), 0))
            )
        ).scalar_one()
        won_amount = (
            await self.db.execute(
                select(func.coalesce(func.sum(Opportunity.estimated_amount), 0)).where(
                    Opportunity.status == "won"
                )
            )
        ).scalar_one()

        total = sum(by_status.values())
        return OpportunityStatsResp(
            total=total,
            open=by_status.get("open", 0),
            won=by_status.get("won", 0),
            lost=by_status.get("lost", 0),
            closed=by_status.get("closed", 0),
            total_amount=Decimal(total_amount or 0),
            won_amount=Decimal(won_amount or 0),
            by_stage=by_stage,
            by_source=by_source,
            by_status=by_status,
        )


__all__ = [
    "STAGES",
    "STAGE_CODES",
    "STAGE_DISPLAY_ORDER",
    "STAGE_LABELS",
    "STAGE_PROBABILITY_MAP",
    "OpportunityService",
    "get_default_probability",
]
