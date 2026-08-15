"""Pydantic models for Clarify plugin."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class ClarifyRule(BaseModel):
    """澄清规则：定义何时触发反问、如何反问、确认后调什么。"""

    rule_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str
    trigger_condition: str = Field(
        description="触发条件，关键词或语义描述，如 '模糊主语' / '缺少时间范围'"
    )
    question_template: str = Field(
        description="反问模板，支持 {slot} 占位符，如 '您说的{subject}具体是指？'"
    )
    confirm_api: str = Field(
        default="",
        description="确认后回调的 API 路径，如 /api/v1/plugins/xxx/execute",
    )
    priority: int = Field(default=0, description="规则优先级，越大越先匹配")
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClarifySession(BaseModel):
    """一次澄清会话：跟踪多轮反问与用户回答。"""

    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    original_question: str = ""
    matched_rule_id: str | None = None
    clarification_round: int = Field(default=0, description="当前澄清轮次")
    max_rounds: int = Field(default=3, description="最大澄清轮次")
    answers: list[dict[str, Any]] = Field(
        default_factory=list,
        description="用户回答历史，每项 {round, question, answer}",
    )
    status: str = Field(
        default="pending",
        description="pending / clarifying / confirmed / abandoned",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DetectRequest(BaseModel):
    """POST /clarify/detect 请求体。"""

    question: str
    context: str = ""
    session_id: str | None = None


class DetectResponse(BaseModel):
    """POST /clarify/detect 响应体。"""

    needs_clarification: bool
    session_id: str
    matched_rule: ClarifyRule | None = None
    question: str = ""
    clarification_round: int = 0


class RespondRequest(BaseModel):
    """POST /clarify/respond 请求体。"""

    session_id: str
    answer: str


class RespondResponse(BaseModel):
    """POST /clarify/respond 响应体。"""

    session_id: str
    status: str
    clarification_round: int
    next_question: str = ""
    confirmed_data: dict[str, Any] | None = None
