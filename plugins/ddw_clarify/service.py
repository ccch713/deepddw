"""Core logic: detect ambiguity → match rule → generate clarification → receive confirmation."""
from __future__ import annotations

import re
from typing import Any

from .models import ClarifyRule, ClarifySession

# ---------------------------------------------------------------------------
# Default built-in rules
# ---------------------------------------------------------------------------

_DEFAULT_RULES: list[ClarifyRule] = [
    ClarifyRule(
        rule_id="ambiguous_subject",
        name="模糊主语",
        trigger_condition="主语模糊|它|那个|这个|东西|情况",
        question_template="您提到的「{subject}」具体是指什么？请补充说明。",
        confirm_api="",
        priority=10,
    ),
    ClarifyRule(
        rule_id="missing_time_range",
        name="缺少时间范围",
        trigger_condition="最近|之前|以后|之前|一直|有时候|偶尔",
        question_template="请问您说的时间范围是？例如「最近一周」或「上个月」。",
        confirm_api="",
        priority=8,
    ),
    ClarifyRule(
        rule_id="missing_quantity",
        name="缺少数量/程度",
        trigger_condition="一些|很多|很少|大量|部分|少量|不少",
        question_template="能否给出更具体的数量或程度？例如「大约 50 件」或「占比 30%」。",
        confirm_api="",
        priority=6,
    ),
    ClarifyRule(
        rule_id="vague_action",
        name="模糊动作",
        trigger_condition="处理一下|看看|弄一下|搞一下|解决一下",
        question_template="请问您期望的具体操作是什么？例如「生成报告」或「发送通知」。",
        confirm_api="",
        priority=5,
    ),
    ClarifyRule(
        rule_id="missing_target",
        name="缺少目标对象",
        trigger_condition="相关|有关|涉及到|关于",
        question_template="能否具体说明涉及哪个对象？例如产品名称、项目编号等。",
        confirm_api="",
        priority=4,
    ),
]


class ClarifyService:
    """检测模糊问题 → 匹配规则 → 生成反问 → 接收确认 → 继续执行。"""

    def __init__(
        self,
        rules: list[ClarifyRule] | None = None,
        max_rounds: int = 3,
    ) -> None:
        self._rules: list[ClarifyRule] = rules if rules is not None else list(_DEFAULT_RULES)
        self._rules.sort(key=lambda r: r.priority, reverse=True)
        self._sessions: dict[str, ClarifySession] = {}
        self._max_rounds = max_rounds

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def list_rules(self) -> list[ClarifyRule]:
        return list(self._rules)

    def add_rule(self, rule: ClarifyRule) -> None:
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority, reverse=True)

    def remove_rule(self, rule_id: str) -> bool:
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.rule_id != rule_id]
        return len(self._rules) < before

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def get_session(self, session_id: str) -> ClarifySession | None:
        return self._sessions.get(session_id)

    def create_session(self, question: str) -> ClarifySession:
        session = ClarifySession(
            original_question=question,
            max_rounds=self._max_rounds,
        )
        self._sessions[session.session_id] = session
        return session

    # ------------------------------------------------------------------
    # Core flow
    # ------------------------------------------------------------------

    def detect(
        self,
        question: str,
        context: str = "",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """检测问题是否模糊，返回是否需要澄清。"""
        session: ClarifySession | None = None
        if session_id:
            session = self._sessions.get(session_id)
        if session is None:
            session = self.create_session(question)

        rule = self._match_rule(question, context)

        if rule is None:
            session.status = "confirmed"
            return {
                "needs_clarification": False,
                "session_id": session.session_id,
                "matched_rule": None,
                "question": "",
                "clarification_round": session.clarification_round,
            }

        session.matched_rule_id = rule.rule_id
        session.status = "clarifying"
        session.clarification_round += 1
        session.updated_at = session.updated_at.__class__.now(session.updated_at.tzinfo)

        filled_question = self._fill_template(rule.question_template, question, context)

        return {
            "needs_clarification": True,
            "session_id": session.session_id,
            "matched_rule": rule,
            "question": filled_question,
            "clarification_round": session.clarification_round,
        }

    def respond(self, session_id: str, answer: str) -> dict[str, Any]:
        """接收用户对反问的回答，决定下一步。"""
        session = self._sessions.get(session_id)
        if session is None:
            return {
                "session_id": session_id,
                "status": "error",
                "clarification_round": 0,
                "next_question": "",
                "confirmed_data": None,
            }

        session.answers.append(
            {
                "round": session.clarification_round,
                "question": self._get_last_question(session),
                "answer": answer,
            }
        )

        # 回答足够明确 → 确认
        if self._is_answer_sufficient(answer):
            session.status = "confirmed"
            return {
                "session_id": session.session_id,
                "status": "confirmed",
                "clarification_round": session.clarification_round,
                "next_question": "",
                "confirmed_data": {
                    "original_question": session.original_question,
                    "answers": session.answers,
                },
            }

        # 达到最大轮次 → 强制确认
        if session.clarification_round >= session.max_rounds:
            session.status = "confirmed"
            return {
                "session_id": session.session_id,
                "status": "confirmed",
                "clarification_round": session.clarification_round,
                "next_question": "",
                "confirmed_data": {
                    "original_question": session.original_question,
                    "answers": session.answers,
                    "forced": True,
                },
            }

        # 继续追问
        session.clarification_round += 1
        next_q = self._generate_follow_up(session, answer)
        return {
            "session_id": session.session_id,
            "status": "clarifying",
            "clarification_round": session.clarification_round,
            "next_question": next_q,
            "confirmed_data": None,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _match_rule(self, question: str, context: str) -> ClarifyRule | None:
        text = f"{question} {context}"
        for rule in self._rules:
            if not rule.enabled:
                continue
            if re.search(rule.trigger_condition, text):
                return rule
        return None

    @staticmethod
    def _fill_template(template: str, question: str, context: str) -> str:
        """尝试用上下文填充模板占位符。"""
        subject = context if context else question[:20]
        return template.replace("{subject}", subject)

    @staticmethod
    def _is_answer_sufficient(answer: str) -> bool:
        """简单启发式：回答长度 ≥ 4 视为足够明确。"""
        return len(answer.strip()) >= 4

    @staticmethod
    def _get_last_question(session: ClarifySession) -> str:
        if session.answers:
            return session.answers[-1].get("question", "")
        return ""

    def _generate_follow_up(self, session: ClarifySession, answer: str) -> str:
        """根据已有回答生成追问。"""
        if session.clarification_round == 2:
            return "请再补充一些细节，例如具体时间、数量或对象名称。"
        return "能否进一步说明您的需求？"
