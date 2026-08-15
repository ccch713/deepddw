"""用量计费测试（2026-08-14 M0-5）。

费率（用户拍板）：token = DeepSeek 涨价后 × 4（输入 800 分/百万、输出 3200 分/百万）；
25 元封顶 + 超限警示记录。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)

from core.database.models import Tenant
from core.database.tenant_filter import tenant_scope

from plugins.ddw_wenqu_tutor.config import BILLING_CAP_CENTS
from plugins.ddw_wenqu_tutor.models import (
    WenquBase,
    WenquMessage,
    WenquSession,
    WenquStudyEvent,
)
from plugins.ddw_wenqu_tutor.services.billing import (
    collect_session_tokens,
    estimate_usage_cents,
    settle_usage,
)
from plugins.ddw_wenqu_tutor.services.session import end_session


def _mk_session(sid: str = "WS-USAGE-1") -> WenquSession:
    return WenquSession(
        id=sid,
        student_name="CXY",
        subject="chemistry",
        status="active",
        started_at=datetime.now(timezone.utc),
        active_seconds=600,
        message_count=2,
    )


@pytest.fixture
async def db_maker():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(WenquBase.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        db.add(Tenant(id=1, name="家庭一"))
        await db.commit()
    yield maker
    await engine.dispose()


@pytest.mark.asyncio
async def test_estimate_usage_cents():
    """费率计算：输入 800 分/百万、输出 3200 分/百万。"""
    # 10 万输入 + 5 万输出 = 80 + 160 = 240 分
    assert estimate_usage_cents(100_000, 50_000) == 240
    # OCR 2 张 × 20 分 + TTS 1000 字 × 15 分/千
    assert estimate_usage_cents(0, 0, ocr_pages=2) == 40
    assert estimate_usage_cents(0, 0, tts_chars=1000) == 15


@pytest.mark.asyncio
async def test_collect_session_tokens(db_maker):
    """消息 token 聚合：assistant=输出，其余=输入。"""
    async with db_maker() as db:
        with tenant_scope(1):
            db.add(_mk_session())
            # 中文 10 字 = 10 token；英文 40 字符 = 10 token
            db.add(WenquMessage(
                session_id="WS-USAGE-1", role="user",
                content="一二三四五六七八九十", token_count=10,
            ))
            db.add(WenquMessage(
                session_id="WS-USAGE-1", role="assistant",
                content="aaaa bbbb cccc dddd eeee ffff gggg hhhh iiii jjjj",
                token_count=10,
            ))
            await db.commit()

            in_t, out_t = await collect_session_tokens(db, "WS-USAGE-1")
            assert in_t == 10
            assert out_t == 10


@pytest.mark.asyncio
async def test_settle_usage_with_cap_warning(db_maker):
    """25 元封顶 + 超限警示记录。"""
    async with db_maker() as db:
        with tenant_scope(1):
            db.add(_mk_session())
            # 巨额 token：输入 3 亿 → 24000 分，超过 2500 分封顶
            db.add(WenquMessage(
                session_id="WS-USAGE-1", role="user",
                content="x", token_count=100_000_000,
            ))
            db.add(WenquMessage(
                session_id="WS-USAGE-1", role="assistant",
                content="y", token_count=100_000_000,
            ))
            await db.commit()

            usage = await settle_usage(db, "WS-USAGE-1")
            assert usage["capped"] is True
            assert usage["charge_cents"] == BILLING_CAP_CENTS
            assert usage["usage_cents"] > BILLING_CAP_CENTS

            # 警示记录已落库
            result = await db.execute(
                select(WenquStudyEvent).where(
                    WenquStudyEvent.event_type == "billing_cap_warning"
                )
            )
            warnings = result.scalars().all()
            assert len(warnings) == 1
            assert "usage_cents" in warnings[0].payload


@pytest.mark.asyncio
async def test_end_session_usage_charge(db_maker):
    """下课结算走用量计费：按 token 用量扣费。"""
    async with db_maker() as db:
        with tenant_scope(1):
            db.add(_mk_session())
            # 输入 10 万 token + 输出 5 万 token
            db.add(WenquMessage(
                session_id="WS-USAGE-1", role="user",
                content="问" * 1000, token_count=100_000,
            ))
            db.add(WenquMessage(
                session_id="WS-USAGE-1", role="assistant",
                content="答" * 500, token_count=50_000,
            ))
            await db.commit()

            class _Wallet:
                def __init__(self):
                    self.calls = []

                async def charge(self, **kw):
                    self.calls.append(kw)
                    return {
                        "txn_no": "TXN-U1",
                        "balance_after_cents": 9900,
                    }

            wallet = _Wallet()
            result = await end_session(db, "WS-USAGE-1", wallet)
            # 10 万×0.8/千 + 5 万×3.2/千 = 80 + 160 = 240 分
            assert result["charge_cents"] == 240
            assert wallet.calls[0]["amount_cents"] == 240
            assert result["txn_no"] == "TXN-U1"
