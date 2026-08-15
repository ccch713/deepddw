"""问渠学科包 ORM 模型 — 9 张表，表前缀 wenqu_。

SQLAlchemy 2.0 Mapped 风格。

租户策略（2026-08-14 分租户改造）：
- 继承核心 Base（core.database.session.Base）→ 共享 registry，底座
  tenant_filter 的自动注入/过滤对问渠表生效（家庭 = 租户）
- 学习数据 6 表继承 TenantMixin → 自动按 tenant_id 隔离
- 题库/教材 3 表不继承 → 平台级共享（白名单外天然共享）
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from core.database.models import TenantMixin
from core.database.session import Base as CoreBase


class WenquBase(CoreBase):
    """问渠模型基类（继承核心 Base，共享 registry 以启用租户自动过滤）。"""

    __abstract__ = True


class WenquSession(TenantMixin, WenquBase):
    """一堂课。"""
    __tablename__ = "wenqu_sessions"

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True
    )  # WS+时间戳
    student_name: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(
        String(16)
    )  # physics|chemistry
    chapter: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16), default="active"
    )  # active|ended|billed
    phase: Mapped[str] = mapped_column(
        String(32), default="info_check"
    )  # 轻量状态机阶段
    # 枚举值：info_check→mode_select→chem_analysis→
    # answer_diag→pinpoint→min_intervention→
    # verify_transfer→record
    started_at: Mapped[datetime]
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True
    )
    active_seconds: Mapped[int] = mapped_column(
        Integer, default=0
    )  # 活跃计时（防挂机）
    message_count: Mapped[int] = mapped_column(
        Integer, default=0
    )
    charge_txn_no: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )  # 钱包扣费流水
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now()
    )


class WenquMessage(TenantMixin, WenquBase):
    """对话消息。"""
    __tablename__ = "wenqu_messages"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    session_id: Mapped[str] = mapped_column(
        String(40), index=True
    )
    role: Mapped[str] = mapped_column(
        String(16)
    )  # system|user|assistant
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now()
    )


class WenquTextbook(WenquBase):
    """教材。"""
    __tablename__ = "wenqu_textbooks"

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True
    )
    subject: Mapped[str] = mapped_column(String(16))
    grade: Mapped[str] = mapped_column(String(8))  # "9"
    version: Mapped[str] = mapped_column(
        String(32)
    )  # "人教版 2024"
    file_path: Mapped[str] = mapped_column(String(256))
    chapters: Mapped[str] = mapped_column(
        Text
    )  # JSON [{title,pages}]
    indexed_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True
    )


class WenquTextbookChunk(WenquBase):
    """教材切片。"""
    __tablename__ = "wenqu_textbook_chunks"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    textbook_id: Mapped[str] = mapped_column(
        String(40), index=True
    )
    chapter: Mapped[str] = mapped_column(String(64))
    page_range: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)


class WenquQuestion(WenquBase):
    """真题。"""
    __tablename__ = "wenqu_questions"

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True
    )
    subject: Mapped[str] = mapped_column(String(16))
    chapter: Mapped[str] = mapped_column(String(64))
    year: Mapped[int] = mapped_column(
        Integer, default=lambda: datetime.now().year
    )  # 题目年份（教改频繁，默认当前年；M1 起可按年份筛选）
    difficulty: Mapped[str] = mapped_column(
        String(16)
    )  # easy|medium|hard
    source: Mapped[str] = mapped_column(String(64))
    # ── M1 题库地域/学校维度（2026-08-14 预留，备案后启用筛选）──
    province: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, default=None
    )  # 省（考纲差异）
    city: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, default=None
    )  # 城市（中考真题按市）
    school: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, default=None
    )  # 上传学生所在学校标签（重点中学题=刷题目标）
    contributor: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, default=None
    )  # 上传者（题库众筹奖励结算）
    question_text: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    explanation: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    knowledge_points: Mapped[str] = mapped_column(
        Text
    )  # JSON list
    mode: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, default=None
    )  # 11 枚举：substance_change|ion_redox|quant_calc|
    # experiment|test_identify|purify_separate|
    # chart_table|process_flow|electrochem|structure|organic
    is_ai_generated: Mapped[bool] = mapped_column(
        Boolean, default=False
    )  # True=AI 生成的变式题
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now()
    )


class WenquAttempt(TenantMixin, WenquBase):
    """答题记录（2026-08-14：挑战/作对判定数据源）。

    每次提交答案记一行：correct=true 表示该生作对过此题
    （挑战模式据此排除已作对的题）。
    """
    __tablename__ = "wenqu_attempts"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    student_name: Mapped[str] = mapped_column(
        String(32), index=True
    )
    question_id: Mapped[str] = mapped_column(
        String(40), index=True
    )
    correct: Mapped[bool] = mapped_column(
        Boolean, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now()
    )


class WenquTheme(WenquBase):
    """皮肤主题（2026-08-14 移植自 wenquK12 皮肤商店）。

    平台共享表（不继承 TenantMixin）：所有学生可见。
    css_vars 使用学习台 CSS 变量体系（--bg/--sidebar/--card/...）。
    """
    __tablename__ = "wenqu_themes"

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True
    )
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(256))
    css_vars: Mapped[str] = mapped_column(Text)  # JSON
    style_tags: Mapped[str] = mapped_column(
        Text, default="[]"
    )  # JSON list
    target_gender: Mapped[str] = mapped_column(
        String(16), default="unisex"
    )  # unisex|female|male
    is_official: Mapped[bool] = mapped_column(
        Boolean, default=False
    )
    is_approved: Mapped[bool] = mapped_column(
        Boolean, default=False
    )  # UGC 待 AI 审核
    price_cents: Mapped[int] = mapped_column(
        Integer, default=0
    )  # 皮肤定价上限 5 元（用户拍板）
    sales_count: Mapped[int] = mapped_column(
        Integer, default=0
    )
    author_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=None
    )
    author_name: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now()
    )


class WenquUserTheme(WenquBase):
    """学生皮肤激活记录（2026-08-14）。"""
    __tablename__ = "wenqu_user_themes"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    student_name: Mapped[str] = mapped_column(
        String(32), index=True
    )
    theme_id: Mapped[str] = mapped_column(
        String(40), index=True
    )
    activated_at: Mapped[datetime] = mapped_column(
        server_default=func.now()
    )


class WenquWrongAnswer(TenantMixin, WenquBase):
    """错题记录。"""
    __tablename__ = "wenqu_wrong_answers"

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True
    )
    student_name: Mapped[str] = mapped_column(String(32))
    question_id: Mapped[str] = mapped_column(
        String(40), index=True
    )
    session_id: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )
    student_answer: Mapped[str] = mapped_column(Text)
    error_type: Mapped[str] = mapped_column(
        String(24)
    )  # concept|calculation|unit|misread
    knowledge_gap: Mapped[str] = mapped_column(
        Text
    )  # 苏格拉底复盘入口
    correct_parts: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None
    )  # 做对了什么
    error_location: Mapped[Optional[str]] = mapped_column(
        String(256), nullable=True, default=None
    )  # 错在哪儿（第一处关键错误位置）
    error_root_cause: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None
    )  # 为什么错（根因）
    check_strategy: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None
    )  # 下次怎么检查
    mode: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, default=None
    )  # 本题模式（回填自 question.mode）
    resolved: Mapped[bool] = mapped_column(
        Boolean, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now()
    )


class WenquProgress(TenantMixin, WenquBase):
    """学习进度。"""
    __tablename__ = "wenqu_progress"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    student_name: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(16))
    chapter: Mapped[str] = mapped_column(String(64))
    total_questions: Mapped[int] = mapped_column(
        Integer, default=0
    )
    completed: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(
        Integer, default=0
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class WenquParentReport(TenantMixin, WenquBase):
    """家长周报。"""
    __tablename__ = "wenqu_parent_reports"

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True
    )
    student_name: Mapped[str] = mapped_column(String(32))
    report_date: Mapped[date] = mapped_column(Date)
    total_minutes: Mapped[int] = mapped_column(Integer)
    questions_attempted: Mapped[int] = mapped_column(Integer)
    new_wrong_count: Mapped[int] = mapped_column(Integer)
    weak_points: Mapped[str] = mapped_column(
        Text
    )  # JSON [{point, rate}]
    summary_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now()
    )


class WenquStudyEvent(TenantMixin, WenquBase):
    """学习事件（计费/审计/周报原始数据）。"""
    __tablename__ = "wenqu_study_events"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    session_id: Mapped[str] = mapped_column(
        String(40), index=True
    )
    event_type: Mapped[str] = mapped_column(
        String(32)
    )  # session_start|message|wrong|redo|session_end
    payload: Mapped[str] = mapped_column(Text)  # JSON
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now()
    )


__all__ = [
    "WenquAttempt",
    "WenquBase",
    "WenquMessage",
    "WenquParentReport",
    "WenquProgress",
    "WenquQuestion",
    "WenquSession",
    "WenquStudyEvent",
    "WenquTextbook",
    "WenquTextbookChunk",
    "WenquTheme",
    "WenquUserTheme",
    "WenquWrongAnswer",
]
