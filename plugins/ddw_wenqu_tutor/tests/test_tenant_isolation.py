"""租户隔离验证（2026-08-14 分租户改造）。

验证：继承 TenantMixin 的 6 张学习表自动注入/过滤 tenant_id；
题库/教材 3 张共享表不带租户字段。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from core.database.models import Tenant
from core.database.tenant_filter import tenant_scope

from plugins.ddw_wenqu_tutor.models import (
    WenquBase,
    WenquParentReport,
    WenquProgress,
    WenquQuestion,
    WenquSession,
    WenquStudyEvent,
    WenquTextbook,
    WenquWrongAnswer,
)

# 学习数据 6 表（应带 tenant_id）
TENANT_AWARE_TABLES = (
    WenquSession,
    WenquWrongAnswer,
    WenquProgress,
    WenquParentReport,
    WenquStudyEvent,
)
# 共享表（不应带 tenant_id）
SHARED_TABLES = (WenquQuestion, WenquTextbook)


def _mk_session(owner: str) -> WenquSession:
    return WenquSession(
        id=f"WS-T{owner}",
        student_name=owner,
        subject="physics",
        status="active",
        started_at=datetime.now(timezone.utc),
        active_seconds=0,
        message_count=0,
    )


@pytest.fixture
def engine():
    eng = create_engine("sqlite://")
    WenquBase.metadata.create_all(eng)
    with Session(eng) as db:
        db.add(Tenant(id=1, name="家庭一"))
        db.add(Tenant(id=2, name="家庭二"))
        db.commit()
    return eng


def test_tenant_auto_inject_and_filter(engine):
    """不同租户写入后查询互相隔离，且自动注入 tenant_id。"""
    with Session(engine) as db:
        with tenant_scope(1):
            db.add(_mk_session("A"))
            db.commit()
        with tenant_scope(2):
            db.add(_mk_session("B"))
            db.commit()

    with Session(engine) as db:
        with tenant_scope(1):
            rows = db.scalars(select(WenquSession)).all()
            assert len(rows) == 1
            assert rows[0].student_name == "A"
            assert rows[0].tenant_id == 1
        with tenant_scope(2):
            rows = db.scalars(select(WenquSession)).all()
            assert len(rows) == 1
            assert rows[0].student_name == "B"
            assert rows[0].tenant_id == 2


def test_tenant_columns_present_on_aware_tables():
    """6 张学习表都有 tenant_id 列。"""
    for model in TENANT_AWARE_TABLES:
        cols = {c.name for c in inspect(model).columns}
        assert "tenant_id" in cols, f"{model.__name__} 缺少 tenant_id"


def test_shared_tables_have_no_tenant(engine):
    """题库/教材共享表不带 tenant_id，平台级数据天然共享。"""
    for model in SHARED_TABLES:
        cols = {c.name for c in inspect(model).columns}
        assert "tenant_id" not in cols, f"{model.__name__} 不应有 tenant_id"

    # 共享表数据跨租户可见（无过滤条件）
    with Session(engine) as db:
        with tenant_scope(1):
            db.add(
                WenquQuestion(
                    id="Q1",
                    subject="chemistry",
                    chapter="燃料",
                    year=2024,
                    difficulty="easy",
                    source="textbook",
                    question_text="测试题干",
                    answer="B",
                    knowledge_points="[]",
                )
            )
            db.commit()
        with tenant_scope(2):
            rows = db.scalars(select(WenquQuestion)).all()
            assert len(rows) == 1
