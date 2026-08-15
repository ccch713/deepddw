"""问渠学科包 Pydantic v2 Schemas。"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class SessionStart(BaseModel):
    """开课请求。"""
    student_name: str = Field(default="CXY", max_length=32)
    subject: Literal["chinese", "math", "english", "physics", "chemistry", "morality", "history"]
    chapter: Optional[str] = None


class SessionOut(BaseModel):
    """开课响应。"""
    session_id: str
    subject: str
    status: str
    started_at: datetime


class MessageSend(BaseModel):
    """发送消息。"""
    content: str = Field(min_length=1, max_length=2000)


class MessageOut(BaseModel):
    """消息输出。"""
    role: str
    content: str
    created_at: datetime


class SessionEndOut(BaseModel):
    """下课响应。"""
    session_id: str
    active_minutes: int
    charge_cents: int  # 本次扣费（分）
    balance_after_cents: int  # 扣后余额
    txn_no: str


class QuestionListOut(BaseModel):
    """题目列表。"""
    items: list[dict]
    total: int


class QuestionSubmit(BaseModel):
    """提交答案。"""
    question_id: str
    student_answer: str
    session_id: Optional[str] = None
    student_name: str = Field(default="CXY", max_length=32)


# 化学错误类型联合
ChemErrorType = Literal[
    "concept", "calculation", "unit", "misread",
    "misread_condition", "wrong_reaction", "overage_missed",
    "conservation_fail", "valence", "electron_transfer",
    "expression",
]

# 化学题目模式
ChemMode = Literal[
    "substance_change", "ion_redox", "quant_calc",
    "experiment", "test_identify", "purify_separate",
    "chart_table", "process_flow", "electrochem",
    "structure", "organic",
]


class FourQuestions(BaseModel):
    """错题四问卡片。"""
    correct_parts: str = Field(description="做对了什么")
    error_location: str = Field(description="错在哪儿")
    error_root_cause: str = Field(description="为什么错")
    check_strategy: str = Field(description="下次怎么检查")


class QuestionSubmitOut(BaseModel):
    """评判结果（修改：新增四问+mode）。"""
    correct: bool
    error_type: Optional[ChemErrorType] = None
    knowledge_gap: Optional[str] = None
    wrong_id: Optional[str] = None
    four_questions: Optional[FourQuestions] = None
    mode: Optional[ChemMode] = None


class GenerateVariantIn(BaseModel):
    """生成变式题请求。"""
    question_id: str
    difficulty: Literal["easy", "medium", "hard"] = "medium"


class GenerateVariantOut(BaseModel):
    """生成变式题响应。"""
    question_id: str
    question_text: str
    answer: str
    explanation: Optional[str] = None
    mode: Optional[ChemMode] = None
    is_ai_generated: bool = True


class FourQuestionsOut(BaseModel):
    """错题四问详情响应。"""
    wrong_id: str
    question_id: str
    student_answer: str
    error_type: Optional[str] = None
    mode: Optional[str] = None
    four_questions: FourQuestions


class SafetyRuleOut(BaseModel):
    """安全规则条目。"""
    id: int
    substance: str
    danger_type: str
    protection: str
    emergency: str


class SafetyRulesListOut(BaseModel):
    """安全规则列表。"""
    rules: list[SafetyRuleOut]
    total: int


class WrongRedoOut(BaseModel):
    """错题复盘（修改：新增四问卡片）。"""
    session_id: str
    first_question: str
    four_questions: Optional[FourQuestions] = None


class ParentStatsOut(BaseModel):
    """家长统计。"""
    total_minutes_week: int
    questions_attempted_week: int
    correct_rate: float
    weak_points: list[dict]
    wrong_trend: list[dict]


__all__ = [
    "ChemErrorType",
    "ChemMode",
    "FourQuestions",
    "FourQuestionsOut",
    "GenerateVariantIn",
    "GenerateVariantOut",
    "MessageOut",
    "MessageSend",
    "ParentStatsOut",
    "QuestionListOut",
    "QuestionSubmit",
    "QuestionSubmitOut",
    "SafetyRuleOut",
    "SafetyRulesListOut",
    "SessionEndOut",
    "SessionOut",
    "SessionStart",
    "WrongRedoOut",
]
