from __future__ import annotations

"""DDW 销售端 AI 副驾驶插件业务逻辑层。

设计要点：

1. **不创建新表**：所有数据走 SQLAlchemy 跨插件 query
   （crm_opportunities / crm_sales_notes / crm_quotations /
   crm_companies / crm_contacts）。

2. **不走租户过滤**：所有端点都通过 ``bypass_tenant_filter()`` 上下文管理器
   运行（与 P0-5 ddw_sales_dashboard 一致）。

3. **AI 推理统一走 ``embedded_llm.engine.EmbeddedLLM``**：
   - 默认 backend = ``_LocalEchoBackend``（``[echo] ...`` 字符串）
   - 生产环境 ``prefer_real=True`` 自动尝试加载 llama.cpp
   - 永不持有 / 硬编码任何 API Key
   - 单次调用失败降级为 echo 字符串（不抛异常，保证端点可用）

4. **确定性指标 + LLM 综合**：风险分数、行动优先级等「可以由规则算出来」的部分
   走纯 Python 计算，避免假性 LLM 输出影响关键决策；「自然语言总结」类
   （reasoning / alert / report）才调 LLM。
"""

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# 跨插件 ORM 模型
from plugins.ddw_company_profile.models import Company
from plugins.ddw_contact_hub.models import Contact
from plugins.ddw_opportunity.models import Opportunity
from plugins.ddw_opportunity.services import STAGE_LABELS, STAGE_PROBABILITY_MAP
from plugins.ddw_quotation.models import Quotation
from plugins.ddw_sales_note.models import SalesNote

from .schemas import (
    ActionSuggestionResp,
    DailyMetrics,
    DailyReportResp,
    RiskAlertResp,
    StageSuggestionResp,
    WeeklyMetrics,
    WeeklyReportResp,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 内部常量 / 工具
# ---------------------------------------------------------------------------


# 阶段推进映射：当前阶段 -> 下一阶段
# won / lost 是终止态，原样返回
_NEXT_STAGE_MAP: dict[str, str] = {
    "initial_contact": "demand_confirmation",
    "demand_confirmation": "proposal_submitted",
    "proposal_submitted": "quotation_sent",
    "quotation_sent": "negotiation",
    "negotiation": "contract_pending",
    "contract_pending": "won",
    "won": "won",
    "lost": "lost",
}

# 用于风险评分的「阶段权重」（越靠前权重越高 = 越需要主动跟进）
_STAGE_RISK_WEIGHTS: dict[str, float] = {
    "initial_contact": 0.3,
    "demand_confirmation": 0.25,
    "proposal_submitted": 0.2,
    "quotation_sent": 0.15,
    "negotiation": 0.15,
    "contract_pending": 0.1,
    "won": 0.0,
    "lost": 0.0,
}


def _next_stage(cur: str) -> str:
    """给定当前阶段，返回管道下一阶段（已终止则原样返回）。"""
    return _NEXT_STAGE_MAP.get(cur, cur)


def _stage_label(code: str) -> str:
    """阶段编码 -> 中文标签。"""
    return STAGE_LABELS.get(code, code)


def _stage_probability(code: str) -> int:
    """阶段编码 -> 默认成单概率。"""
    return STAGE_PROBABILITY_MAP.get(code, 0)


def _utcnow() -> datetime:
    """当前 UTC 时间（带 tzinfo，避免 naive/aware 混用）。"""
    return datetime.now(timezone.utc)


def _ensure_aware_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """把 datetime 统一成 UTC-aware。naive 视为 UTC。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _stale_days(updated_at: Optional[datetime], now: Optional[datetime] = None) -> int:
    """计算「距离最近一次活动」天数。updated_at 为空时返回 9999（视为极度停滞）。"""
    if updated_at is None:
        return 9999
    now = now or _utcnow()
    updated_at = _ensure_aware_utc(updated_at)
    delta = now - updated_at
    return max(0, delta.days)


# ---------------------------------------------------------------------------
# LLM 客户端（懒加载 + 失败降级）
# ---------------------------------------------------------------------------


_LLM_SINGLETON: Any = None
_LLM_LOCK = None  # 不引入 asyncio.Lock；服务是 stateless，懒加载即可


def _get_llm() -> Any:
    """懒加载获取平台 EmbeddedLLM 实例。

    - 默认 ``prefer_real=False``：测试 / 离线环境走 echo backend
    - 生产环境由 manifest / 平台配置决定（暂不切换）
    - 单例：避免每个端点都重建 backend
    """
    global _LLM_SINGLETON
    if _LLM_SINGLETON is not None:
        return _LLM_SINGLETON
    try:
        from plugins.embedded_llm.engine import EmbeddedLLM

        # 注意：prefer_real=False 保证测试环境 100% 走 echo backend，
        # 不依赖是否安装 llama_cpp / 是否有 GGUF 模型。
        _LLM_SINGLETON = EmbeddedLLM(
            model_name="ddw-sales-copilot",
            prefer_real=False,
        )
        logger.info("EmbeddedLLM initialized (backend=%s)", type(_LLM_SINGLETON._backend).__name__)
    except Exception as e:  # noqa: BLE001  # pragma: no cover
        logger.warning("EmbeddedLLM init failed: %s; fallback to _LocalEchoBackend", e)
        # 极端降级：直接用 echo backend（不依赖 import 顺序）
        from plugins.embedded_llm.engine import _LocalEchoBackend

        class _StubLLM:
            def __init__(self) -> None:
                self._backend = _LocalEchoBackend()

            async def chat(self, prompt: str, system: str = "") -> str:
                return self._backend.generate(prompt, system, 512)

        _LLM_SINGLETON = _StubLLM()
    return _LLM_SINGLETON


async def _llm_chat(prompt: str, system: str = "") -> str:
    """统一的 LLM 调用入口。失败降级为 echo 字符串（绝不抛异常）。"""
    try:
        llm = _get_llm()
        return await llm.chat(prompt, system=system)
    except Exception as e:  # noqa: BLE001  # pragma: no cover
        logger.warning("LLM call failed: %s; fallback to echo", e)
        return f"[echo-fallback] prompt={prompt[:50]!r}"


# ---------------------------------------------------------------------------
# CopilotService
# ---------------------------------------------------------------------------


class CopilotService:
    """销售端 AI 副驾驶业务服务。

    所有方法都接收 ``tenant_id`` 显式参数（与 P0-5 dashboard 一致），
    避免内部隐式上下文依赖。
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # 内部：跨插件数据查询
    # ------------------------------------------------------------------ #

    async def _get_opportunity(self, opportunity_id: int, tenant_id: int) -> Opportunity | None:
        return (
            await self.db.execute(
                select(Opportunity).where(
                    Opportunity.id == opportunity_id,
                    Opportunity.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()

    async def _get_company(self, company_id: int, tenant_id: int) -> Company | None:
        return (
            await self.db.execute(
                select(Company).where(
                    Company.id == company_id,
                    Company.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()

    async def _recent_notes_for_opportunity(
        self, opportunity_id: int, tenant_id: int, limit: int = 5
    ) -> list[SalesNote]:
        rows = (
            await self.db.execute(
                select(SalesNote)
                .where(
                    SalesNote.opportunity_id == opportunity_id,
                    SalesNote.tenant_id == tenant_id,
                )
                .order_by(SalesNote.visit_date.desc().nullslast(), SalesNote.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return list(rows)

    async def _quotations_for_opportunity(
        self, opportunity_id: int, tenant_id: int
    ) -> list[Quotation]:
        rows = (
            await self.db.execute(
                select(Quotation).where(
                    Quotation.opportunity_id == opportunity_id,
                    Quotation.tenant_id == tenant_id,
                )
            )
        ).scalars().all()
        return list(rows)

    # ------------------------------------------------------------------ #
    # 1. Stage Suggestion
    # ------------------------------------------------------------------ #

    async def stage_suggestion(
        self, opportunity_id: int, tenant_id: int = 1
    ) -> StageSuggestionResp | None:
        """基于商机 + 最近拜访记录，LLM 推荐下一阶段。

        找不到商机时返回 ``None``，由 router 抛 404。
        """
        opp = await self._get_opportunity(opportunity_id, tenant_id)
        if opp is None:
            return None

        notes = await self._recent_notes_for_opportunity(opportunity_id, tenant_id, limit=5)

        # 确定性建议：管道下一阶段（兜底）
        next_stage = _next_stage(opp.stage)
        # 若 LLM 推荐与管道一致，节省一次调用？—— 不简化，统一走 LLM 透明可解释
        prompt = self._build_stage_prompt(opp, notes)
        reasoning = await _llm_chat(
            prompt,
            system=(
                "你是 DDW 销售端 AI 副驾驶，"
                "请基于商机信息 + 沟通记录给出阶段推进建议。"
                "回答简洁，不超过 100 字。"
            ),
        )

        return StageSuggestionResp(
            tenant_id=tenant_id,
            opportunity_id=opportunity_id,
            opportunity_name=opp.name,
            current_stage=opp.stage,
            current_stage_label=_stage_label(opp.stage),
            suggested_stage=next_stage,
            suggested_stage_label=_stage_label(next_stage),
            probability=_stage_probability(next_stage),
            reasoning=reasoning,
            recent_notes_count=len(notes),
            last_activity_at=_ensure_aware_utc(opp.updated_at),
        )

    @staticmethod
    def _build_stage_prompt(opp: Opportunity, notes: list[SalesNote]) -> str:
        lines: list[str] = []
        lines.append(f"商机名称：{opp.name}")
        lines.append(f"当前阶段：{opp.stage}（{_stage_label(opp.stage)}）")
        lines.append(f"当前成单概率：{opp.probability}%")
        if opp.estimated_amount is not None:
            lines.append(f"预计金额：{opp.estimated_amount}")
        if opp.expected_close_date:
            lines.append(f"预计成交日：{opp.expected_close_date}")
        if opp.description:
            lines.append(f"描述：{opp.description[:200]}")
        lines.append("")
        lines.append(f"最近 {len(notes)} 条沟通记录：")
        if not notes:
            lines.append("（暂无沟通记录）")
        else:
            for i, n in enumerate(notes, 1):
                d = n.visit_date or n.created_at
                title = n.title or n.note_type
                lines.append(
                    f"  {i}. [{d}] {n.note_type} - {title}：{n.content[:120]}"
                )
        lines.append("")
        lines.append("请基于以上信息判断该商机是否应推进到下一阶段，给出 1-2 句推理。")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # 2. Risk Alert
    # ------------------------------------------------------------------ #

    async def risk_alert(
        self,
        opportunity_id: Optional[int] = None,
        company_id: Optional[int] = None,
        tenant_id: int = 1,
    ) -> RiskAlertResp | None:
        """风险提示。

        优先级：
        1. opportunity_id 不为空 → 取该商机
        2. 否则 company_id 不为空 → 取该企业下「进行中 + 风险最高」商机
        3. 都没有 → 返回 None
        """
        opp: Opportunity | None = None
        company: Company | None = None

        if opportunity_id is not None:
            opp = await self._get_opportunity(opportunity_id, tenant_id)
            if opp is None:
                return None
            if opp.company_id is not None:
                company = await self._get_company(opp.company_id, tenant_id)
        elif company_id is not None:
            company = await self._get_company(company_id, tenant_id)
            if company is None:
                return None
            # 取该企业下进行中的最近更新商机
            opp = (
                await self.db.execute(
                    select(Opportunity)
                    .where(
                        Opportunity.company_id == company_id,
                        Opportunity.tenant_id == tenant_id,
                        Opportunity.status == "open",
                    )
                    .order_by(Opportunity.updated_at.desc().nullslast(), Opportunity.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        else:
            return None

        # ---- 确定性风险计算 ----
        now = _utcnow()
        updated_at = opp.updated_at if opp else None
        # 拜访记录的最近时间
        last_note_at: Optional[datetime] = None
        if opp is not None:
            last_note = (
                await self.db.execute(
                    select(SalesNote.visit_date)
                    .where(
                        SalesNote.opportunity_id == opp.id,
                        SalesNote.tenant_id == tenant_id,
                        SalesNote.visit_date.isnot(None),
                    )
                    .order_by(SalesNote.visit_date.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            last_note_at = last_note

        # 综合最近活动时间（商机 updated_at 与 最后一次拜访的较新者）
        last_activity = _latest_dt([updated_at, last_note_at])
        stale_days = _stale_days(last_activity, now=now)

        # 风险因素列表（命中即加入）
        factors: list[str] = []
        score = 0.0

        # 1) 停滞天数
        if stale_days >= 14:
            factors.append(f"stale_for_{stale_days}_days")
            score += 0.5
        elif stale_days >= 7:
            factors.append(f"stale_for_{stale_days}_days")
            score += 0.3
        elif stale_days >= 4:
            factors.append(f"stale_for_{stale_days}_days")
            score += 0.15

        # 2) 阶段权重
        if opp is not None:
            stage_w = _STAGE_RISK_WEIGHTS.get(opp.stage, 0.0)
            score += stage_w
            if stage_w >= 0.2:
                factors.append(f"early_stage_{opp.stage}")

        # 3) 接近预期成交日但还未推进
        if opp is not None and opp.expected_close_date is not None:
            days_to_close = (opp.expected_close_date - now.date()).days
            if 0 <= days_to_close <= 7 and opp.status == "open":
                factors.append("approaching_close_date")
                score += 0.2

        # 4) 没有任何拜访记录
        if opp is not None and last_note_at is None:
            factors.append("no_visit_records")
            score += 0.1

        # 5) 报价单已发出但 > 14 天无反馈
        if opp is not None:
            last_sent_q = (
                await self.db.execute(
                    select(func.max(Quotation.sent_at))
                    .where(
                        Quotation.opportunity_id == opp.id,
                        Quotation.tenant_id == tenant_id,
                        Quotation.sent_at.isnot(None),
                    )
                )
            ).scalar_one()
            if last_sent_q is not None:
                last_sent = _ensure_aware_utc(last_sent_q)
                if last_sent is not None and (now - last_sent).days >= 14:
                    factors.append("quotation_no_response_14d")
                    score += 0.15

        # ---- 风险等级 ----
        if score >= 0.5:
            level = "high"
        elif score >= 0.25:
            level = "medium"
        else:
            level = "low"

        # ---- LLM 综合告警 ----
        alert_prompt = self._build_risk_prompt(opp, company, stale_days, factors, level)
        alert = await _llm_chat(
            alert_prompt,
            system=(
                "你是 DDW 销售端 AI 副驾驶的「风险预警模块」，"
                "请基于给定的客观指标，输出一句精炼的中文告警（不超过 60 字）。"
            ),
        )

        return RiskAlertResp(
            tenant_id=tenant_id,
            opportunity_id=opp.id if opp else None,
            company_id=company.id if company else None,
            opportunity_name=opp.name if opp else "",
            company_name=company.name if company else "",
            risk_level=level,
            risk_score=round(min(score, 1.0), 4),
            risk_factors=factors,
            stale_days=stale_days if stale_days < 9999 else 0,
            last_activity_at=_ensure_aware_utc(last_activity),
            alert=alert,
        )

    @staticmethod
    def _build_risk_prompt(
        opp: Opportunity | None,
        company: Company | None,
        stale_days: int,
        factors: list[str],
        level: str,
    ) -> str:
        lines: list[str] = []
        lines.append(f"风险等级（系统判定）：{level}")
        if opp is not None:
            lines.append(f"商机：{opp.name}（{opp.stage} / {opp.status}）")
            if opp.expected_close_date:
                lines.append(f"预计成交日：{opp.expected_close_date}")
        if company is not None:
            lines.append(f"客户：{company.name}")
        lines.append(f"停滞天数：{stale_days}")
        lines.append(f"风险因素：{factors if factors else '（无）'}")
        lines.append("")
        lines.append("请输出一句中文告警 + 1 条具体行动建议。")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # 3. Action Suggestion
    # ------------------------------------------------------------------ #

    async def action_suggestion(
        self, opportunity_id: int, tenant_id: int = 1
    ) -> ActionSuggestionResp | None:
        """基于商机 + 拜访 + 报价，生成 3~5 条可执行动作。"""
        opp = await self._get_opportunity(opportunity_id, tenant_id)
        if opp is None:
            return None
        notes = await self._recent_notes_for_opportunity(opportunity_id, tenant_id, limit=5)
        quotations = await self._quotations_for_opportunity(opportunity_id, tenant_id)

        # 确定性上下文
        context: dict[str, Any] = {
            "stage": opp.stage,
            "stage_label": _stage_label(opp.stage),
            "status": opp.status,
            "estimated_amount": float(opp.estimated_amount) if opp.estimated_amount is not None else None,
            "probability": opp.probability,
            "expected_close_date": opp.expected_close_date.isoformat() if opp.expected_close_date else None,
            "notes_count": len(notes),
            "last_note_at": (
                max((n.visit_date or n.created_at for n in notes), default=None)
            ).isoformat() if notes else None,
            "quotations_count": len(quotations),
            "quotation_statuses": [q.status for q in quotations],
            "stale_days": _stale_days(opp.updated_at),
        }

        # LLM 综合
        prompt = self._build_action_prompt(opp, notes, quotations)
        llm_out = await _llm_chat(
            prompt,
            system=(
                "你是 DDW 销售端 AI 副驾驶的「行动建议模块」。"
                "请基于商机阶段 + 沟通记录 + 报价状态，"
                "按优先级倒序输出 3~5 条**具体可执行**的下一步动作。"
                "要求：1) 每条以动词开头；2) 中文；3) 不超过 200 字总长。"
            ),
        )

        # 确定性动作清单（fallback / 解析失败时使用）
        fallback_actions = self._fallback_actions(opp, notes, quotations)
        # 优先尝试从 LLM 输出解析行（每行一条）；失败则用 fallback
        actions = self._parse_actions(llm_out) or fallback_actions

        # 优先级：基于阶段 + stale_days 决定
        priority = self._derive_priority(opp, context["stale_days"])

        return ActionSuggestionResp(
            tenant_id=tenant_id,
            opportunity_id=opportunity_id,
            opportunity_name=opp.name,
            current_stage=opp.stage,
            current_stage_label=_stage_label(opp.stage),
            priority=priority,
            actions=actions,
            reasoning=llm_out,
            context_summary=context,
        )

    @staticmethod
    def _build_action_prompt(
        opp: Opportunity, notes: list[SalesNote], quotations: list[Quotation]
    ) -> str:
        lines: list[str] = []
        lines.append(f"商机：{opp.name}（阶段={opp.stage}，状态={opp.status}，概率={opp.probability}%）")
        if opp.estimated_amount is not None:
            lines.append(f"预计金额：{opp.estimated_amount}")
        if opp.expected_close_date:
            lines.append(f"预计成交日：{opp.expected_close_date}")
        lines.append("")
        lines.append(f"最近 {len(notes)} 条沟通记录：")
        if not notes:
            lines.append("（暂无）")
        else:
            for i, n in enumerate(notes, 1):
                d = n.visit_date or n.created_at
                lines.append(
                    f"  {i}. [{d}] {n.note_type} - {n.title or ''}：{n.content[:80]}"
                )
        lines.append("")
        lines.append(f"报价单（{len(quotations)} 张）：")
        if not quotations:
            lines.append("（暂无）")
        else:
            for q in quotations[:5]:
                lines.append(
                    f"  - {q.quotation_no} 状态={q.status} 金额={q.final_amount}"
                )
        lines.append("")
        lines.append("请按优先级倒序输出 3~5 条**具体可执行**的下一步动作（每行一条）。")
        return "\n".join(lines)

    @staticmethod
    def _fallback_actions(
        opp: Opportunity, notes: list[SalesNote], quotations: list[Quotation]
    ) -> list[str]:
        """确定性动作清单（LLM 解析失败时使用）。"""
        acts: list[str] = []
        if not notes:
            acts.append("电话联系客户，安排首次沟通")
        if opp.stage in ("initial_contact", "demand_confirmation"):
            acts.append("发送产品介绍 + 案例资料")
            acts.append("邀请客户参加线上演示")
        if opp.stage in ("proposal_submitted", "quotation_sent") and not quotations:
            acts.append("准备并发送报价单")
        if quotations and all(q.status == "draft" for q in quotations):
            acts.append("将已拟好的报价单发送给客户")
        if quotations and any(q.status == "sent" for q in quotations):
            acts.append("主动跟进客户对报价的反馈")
        if opp.stage in ("negotiation", "contract_pending"):
            acts.append("安排商务谈判会议")
            acts.append("与法务确认合同条款")
        # 兜底：3 条默认
        if len(acts) < 3:
            acts.extend([
                "更新商机阶段与预计成交日",
                "复盘最近沟通记录，提炼关键需求",
            ])
        return acts[:5]

    @staticmethod
    def _parse_actions(llm_out: str) -> list[str]:
        """从 LLM 输出解析行（每行一条动作）。

        解析规则：按行切，过滤空行与过短行；如果少于 2 条则视为解析失败。
        """
        if not llm_out:
            return []
        lines = [ln.strip() for ln in llm_out.splitlines() if ln.strip()]
        # 去掉编号前缀 "1. " / "1) " / "- "
        cleaned: list[str] = []
        for ln in lines:
            import re

            ln2 = re.sub(r"^[\d]+[.)\s]+", "", ln)
            ln2 = re.sub(r"^[-•·]\s*", "", ln2)
            ln2 = ln2.strip()
            if 4 <= len(ln2) <= 80:
                cleaned.append(ln2)
        return cleaned if len(cleaned) >= 2 else []

    @staticmethod
    def _derive_priority(opp: Opportunity, stale_days: int) -> str:
        """综合优先级：基于阶段紧迫度 + 停滞天数。"""
        if opp.status in ("won", "lost"):
            return "low"
        if stale_days >= 14 or opp.stage in ("contract_pending", "negotiation"):
            return "high"
        if stale_days >= 7 or opp.stage in ("quotation_sent", "proposal_submitted"):
            return "medium"
        return "low"

    # ------------------------------------------------------------------ #
    # 4. Daily Report
    # ------------------------------------------------------------------ #

    async def daily_report(
        self, user_id: int, day: date, tenant_id: int = 1
    ) -> DailyReportResp:
        """聚合某销售某日的工作指标，LLM 生成结构化日报。"""
        start_dt = datetime.combine(day, time.min, tzinfo=timezone.utc)
        end_dt = start_dt + timedelta(days=1)

        # ---- 指标 ----
        # 1) 当日新增商机（created_at 落在 [start_dt, end_dt) 内）
        opp_created = (
            await self.db.execute(
                select(func.count(Opportunity.id)).where(
                    Opportunity.tenant_id == tenant_id,
                    Opportunity.owner_id == user_id,
                    Opportunity.created_at >= start_dt,
                    Opportunity.created_at < end_dt,
                )
            )
        ).scalar_one()

        # 2) 当日有更新的商机
        opp_updated = (
            await self.db.execute(
                select(func.count(Opportunity.id)).where(
                    Opportunity.tenant_id == tenant_id,
                    Opportunity.owner_id == user_id,
                    Opportunity.updated_at >= start_dt,
                    Opportunity.updated_at < end_dt,
                )
            )
        ).scalar_one()

        # 3) 当日新增联系人（无 owner_id，按 created_by）
        new_contacts = (
            await self.db.execute(
                select(func.count(Contact.id)).where(
                    Contact.tenant_id == tenant_id,
                    Contact.created_by == user_id,
                    Contact.created_at >= start_dt,
                    Contact.created_at < end_dt,
                )
            )
        ).scalar_one()

        # 4) 当日新增报价单（按 created_at）
        new_quotations = (
            await self.db.execute(
                select(func.count(Quotation.id)).where(
                    Quotation.tenant_id == tenant_id,
                    Quotation.created_by == user_id,
                    Quotation.created_at >= start_dt,
                    Quotation.created_at < end_dt,
                )
            )
        ).scalar_one()

        # 5) 当日沟通记录（按 created_at）
        notes_rows = (
            await self.db.execute(
                select(SalesNote.note_type, func.count(SalesNote.id))
                .where(
                    SalesNote.tenant_id == tenant_id,
                    SalesNote.user_id == user_id,
                    SalesNote.created_at >= start_dt,
                    SalesNote.created_at < end_dt,
                )
                .group_by(SalesNote.note_type)
            )
        ).all()
        notes_total = sum(int(c) for _t, c in notes_rows)
        notes_by_type: dict[str, int] = {t: int(c) for t, c in notes_rows}

        metrics = DailyMetrics(
            opportunities_created=int(opp_created or 0),
            opportunities_updated=int(opp_updated or 0),
            new_contacts=int(new_contacts or 0),
            new_quotations=int(new_quotations or 0),
            new_notes=notes_total,
            notes_visit=notes_by_type.get("visit", 0),
            notes_call=notes_by_type.get("call", 0),
            notes_meeting=notes_by_type.get("meeting", 0),
        )

        # ---- 确定性亮点 ----
        highlights: list[str] = []
        if metrics.opportunities_created > 0:
            highlights.append(f"新增 {metrics.opportunities_created} 个商机")
        if metrics.new_notes > 0:
            highlights.append(f"记录 {metrics.new_notes} 条沟通")
        if metrics.new_quotations > 0:
            highlights.append(f"出具 {metrics.new_quotations} 张报价单")
        if metrics.new_contacts > 0:
            highlights.append(f"新增 {metrics.new_contacts} 个联系人")

        # ---- LLM 报告 ----
        prompt = (
            f"用户 {user_id} 在 {day.isoformat()} 的工作日报：\n"
            f"指标：{metrics.model_dump()}\n"
            f"亮点：{highlights if highlights else '（当日暂无突出工作）'}\n"
            "请基于以上数据生成结构化日报（包含「今日完成 / 关键数据 / 明日计划」3 段，"
            "中文，200 字以内）。"
        )
        report = await _llm_chat(
            prompt,
            system=(
                "你是 DDW 销售端 AI 副驾驶的「日报生成模块」。"
                "请用简洁的中文输出，结构清晰，避免冗余。"
            ),
        )

        return DailyReportResp(
            tenant_id=tenant_id,
            user_id=user_id,
            date=day,
            metrics=metrics,
            highlights=highlights,
            report=report,
        )

    # ------------------------------------------------------------------ #
    # 5. Weekly Report
    # ------------------------------------------------------------------ #

    async def weekly_report(
        self, user_id: int, week_start: date, tenant_id: int = 1
    ) -> WeeklyReportResp:
        """聚合某销售本周的工作指标，LLM 生成结构化周报。"""
        # week_start 必须是周一；不强制校验，按调用方约定
        week_end = week_start + timedelta(days=6)
        start_dt = datetime.combine(week_start, time.min, tzinfo=timezone.utc)
        end_dt = datetime.combine(week_end + timedelta(days=1), time.min, tzinfo=timezone.utc)

        # 1) 本周新增商机
        opp_created = (
            await self.db.execute(
                select(func.count(Opportunity.id)).where(
                    Opportunity.tenant_id == tenant_id,
                    Opportunity.owner_id == user_id,
                    Opportunity.created_at >= start_dt,
                    Opportunity.created_at < end_dt,
                )
            )
        ).scalar_one()

        # 2) 本周有更新商机
        opp_updated = (
            await self.db.execute(
                select(func.count(Opportunity.id)).where(
                    Opportunity.tenant_id == tenant_id,
                    Opportunity.owner_id == user_id,
                    Opportunity.updated_at >= start_dt,
                    Opportunity.updated_at < end_dt,
                )
            )
        ).scalar_one()

        # 3) 本周成交 / 丢单（按 won_at / 任意 status 切换时间难定位，简化为 won_at + updated_at 联合）
        #    成交：won_at 在本周
        opp_won = (
            await self.db.execute(
                select(func.count(Opportunity.id)).where(
                    Opportunity.tenant_id == tenant_id,
                    Opportunity.owner_id == user_id,
                    Opportunity.status == "won",
                    Opportunity.won_at >= start_dt,
                    Opportunity.won_at < end_dt,
                )
            )
        ).scalar_one()

        opp_lost = (
            await self.db.execute(
                select(func.count(Opportunity.id)).where(
                    Opportunity.tenant_id == tenant_id,
                    Opportunity.owner_id == user_id,
                    Opportunity.status == "lost",
                    Opportunity.updated_at >= start_dt,
                    Opportunity.updated_at < end_dt,
                )
            )
        ).scalar_one()

        new_contacts = (
            await self.db.execute(
                select(func.count(Contact.id)).where(
                    Contact.tenant_id == tenant_id,
                    Contact.created_by == user_id,
                    Contact.created_at >= start_dt,
                    Contact.created_at < end_dt,
                )
            )
        ).scalar_one()

        new_quotations = (
            await self.db.execute(
                select(func.count(Quotation.id)).where(
                    Quotation.tenant_id == tenant_id,
                    Quotation.created_by == user_id,
                    Quotation.created_at >= start_dt,
                    Quotation.created_at < end_dt,
                )
            )
        ).scalar_one()

        notes_rows = (
            await self.db.execute(
                select(SalesNote.note_type, func.count(SalesNote.id))
                .where(
                    SalesNote.tenant_id == tenant_id,
                    SalesNote.user_id == user_id,
                    SalesNote.created_at >= start_dt,
                    SalesNote.created_at < end_dt,
                )
                .group_by(SalesNote.note_type)
            )
        ).all()
        notes_total = sum(int(c) for _t, c in notes_rows)
        notes_by_type: dict[str, int] = {t: int(c) for t, c in notes_rows}

        metrics = WeeklyMetrics(
            opportunities_created=int(opp_created or 0),
            opportunities_updated=int(opp_updated or 0),
            opportunities_won=int(opp_won or 0),
            opportunities_lost=int(opp_lost or 0),
            new_contacts=int(new_contacts or 0),
            new_quotations=int(new_quotations or 0),
            new_notes=notes_total,
            notes_visit=notes_by_type.get("visit", 0),
            notes_call=notes_by_type.get("call", 0),
            notes_meeting=notes_by_type.get("meeting", 0),
        )

        # ---- 确定性亮点 ----
        highlights: list[str] = []
        if metrics.opportunities_won > 0:
            highlights.append(f"成交 {metrics.opportunities_won} 单")
        if metrics.opportunities_lost > 0:
            highlights.append(f"丢单 {metrics.opportunities_lost} 单（建议复盘）")
        if metrics.opportunities_created > 0:
            highlights.append(f"新增 {metrics.opportunities_created} 个商机")
        if metrics.new_notes > 0:
            highlights.append(f"记录 {metrics.new_notes} 条沟通")
        if metrics.new_quotations > 0:
            highlights.append(f"出具 {metrics.new_quotations} 张报价单")
        if metrics.new_contacts > 0:
            highlights.append(f"新增 {metrics.new_contacts} 个联系人")

        # ---- LLM 周报 ----
        prompt = (
            f"用户 {user_id} 在 {week_start.isoformat()} ~ {week_end.isoformat()} 的周报：\n"
            f"指标：{metrics.model_dump()}\n"
            f"亮点：{highlights if highlights else '（本周暂无突出工作）'}\n"
            "请基于以上数据生成结构化周报（包含「本周完成 / 关键数据 / 风险提示 / 下周计划」"
            "4 段，中文，400 字以内）。"
        )
        report = await _llm_chat(
            prompt,
            system=(
                "你是 DDW 销售端 AI 副驾驶的「周报生成模块」。"
                "请用简洁的中文输出，结构清晰，避免冗余。"
            ),
        )

        return WeeklyReportResp(
            tenant_id=tenant_id,
            user_id=user_id,
            week_start=week_start,
            week_end=week_end,
            metrics=metrics,
            highlights=highlights,
            report=report,
        )


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _latest_dt(dts: list[Optional[datetime]]) -> Optional[datetime]:
    """返回最近的非空 datetime（统一 UTC-aware）。"""
    aware: list[datetime] = []
    for d in dts:
        a = _ensure_aware_utc(d)
        if a is not None:
            aware.append(a)
    return max(aware) if aware else None


__all__ = ["CopilotService"]
