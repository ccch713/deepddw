"""会话生命周期 + 活跃计时 + 钱包计费对接。"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wenqu_tutor.config import (
    ACTIVE_TIMEOUT_SECONDS,
)
from plugins.ddw_wenqu_tutor.models import (
    WenquMessage,
    WenquSession,
    WenquStudyEvent,
)


def generate_session_id() -> str:
    """生成会话 ID：WS + 时间戳 + 随机后缀。"""
    ts = int(time.time() * 1000)
    suffix = uuid.uuid4().hex[:8]
    return f"WS{ts}{suffix}"


async def create_session(
    db: AsyncSession,
    student_name: str,
    subject: str,
    chapter: Optional[str] = None,
) -> WenquSession:
    """创建新会话。"""
    session = WenquSession(
        id=generate_session_id(),
        student_name=student_name,
        subject=subject,
        chapter=chapter,
        status="active",
        started_at=datetime.now(timezone.utc),
        active_seconds=0,
        message_count=0,
    )
    db.add(session)
    # 记录学习事件
    event = WenquStudyEvent(
        session_id=session.id,
        event_type="session_start",
        payload=f'{{"student":"{student_name}","subject":"{subject}"}}',
    )
    db.add(event)
    await db.commit()
    return session


async def get_session(
    db: AsyncSession, session_id: str
) -> Optional[WenquSession]:
    """获取会话。"""
    result = await db.execute(
        select(WenquSession).where(
            WenquSession.id == session_id
        )
    )
    return result.scalar_one_or_none()


async def add_message(
    db: AsyncSession,
    session_id: str,
    role: str,
    content: str,
    token_count: int = 0,
) -> WenquMessage:
    """添加消息并更新会话计数和活跃时间。"""
    msg = WenquMessage(
        session_id=session_id,
        role=role,
        content=content,
        token_count=token_count,
    )
    db.add(msg)
    # 更新会话消息计数
    await db.execute(
        update(WenquSession)
        .where(WenquSession.id == session_id)
        .values(
            message_count=WenquSession.message_count + 1
        )
    )
    # 记录消息事件
    event = WenquStudyEvent(
        session_id=session_id,
        event_type="message",
        payload=f'{{"role":"{role}","len":{len(content)}}}',
    )
    db.add(event)
    await db.commit()
    return msg


async def update_active_seconds(
    db: AsyncSession,
    session_id: str,
    last_message_time: float,
) -> int:
    """更新活跃秒数（防挂机：无消息 90s 暂停计时）。"""
    now = time.time()
    elapsed = now - last_message_time
    if elapsed > ACTIVE_TIMEOUT_SECONDS:
        return 0  # 超时，不累计
    session = await get_session(db, session_id)
    if not session:
        return 0
    new_seconds = session.active_seconds + int(elapsed)
    await db.execute(
        update(WenquSession)
        .where(WenquSession.id == session_id)
        .values(active_seconds=new_seconds)
    )
    await db.commit()
    return int(elapsed)


async def get_messages(
    db: AsyncSession, session_id: str
) -> list[WenquMessage]:
    """获取会话所有消息。"""
    result = await db.execute(
        select(WenquMessage)
        .where(WenquMessage.session_id == session_id)
        .order_by(WenquMessage.created_at)
    )
    return list(result.scalars().all())


async def end_session(
    db: AsyncSession,
    session_id: str,
    wallet_client,
) -> dict:
    """下课结算：活跃计时 → 钱包扣费（幂等）。

    Returns:
        dict with keys: active_minutes, charge_cents,
        balance_after_cents, txn_no
    """
    session = await get_session(db, session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")
    if session.status != "active":
        raise ValueError(
            f"Session {session_id} already {session.status}"
        )

    # 计算活跃分钟（向上取整，仅展示）
    active_minutes = max(
        1, (session.active_seconds + 59) // 60
    )

    # ── M0-5 用量计费：token × 单价，25 元封顶 ──
    from plugins.ddw_wenqu_tutor.services.billing import (
        settle_usage,
    )

    usage = await settle_usage(db, session_id)
    charge_cents = usage["charge_cents"]

    # 调钱包扣费（幂等 ref_id=session_id）——必须先成功再标 billed，失败保持 active 可重试
    try:
        result = await wallet_client.charge(
            user_id=session.student_name,
            charge_type="study_time",
            subject=session.subject,
            ref_id=session_id,
            ref_type="session",
            amount_cents=charge_cents,
        )
        txn_no = result.get("txn_no", "")
        balance_after = result.get(
            "balance_after_cents", 0
        )
    except Exception as e:
        # 扣费失败：保持 active（可重试），记录错误事件，不静默
        event = WenquStudyEvent(
            session_id=session_id,
            event_type="charge_error",
            payload=f'{{"error":"{str(e)}"}}',
        )
        db.add(event)
        raise ValueError(f"wallet charge failed: {e}") from e

    # 扣费成功 → 标 billed
    await db.execute(
        update(WenquSession)
        .where(WenquSession.id == session_id)
        .values(
            status="billed",
            charge_txn_no=txn_no,
        )
    )

    # 记录下课事件（含用量明细，审计留痕）
    event = WenquStudyEvent(
        session_id=session_id,
        event_type="session_end",
        payload=(
            f'{{"active_minutes":{active_minutes},'
            f'"charge_cents":{charge_cents},'
            f'"in_tokens":{usage["in_tokens"]},'
            f'"out_tokens":{usage["out_tokens"]},'
            f'"usage_cents":{usage["usage_cents"]},'
            f'"capped":{str(usage["capped"]).lower()},'
            f'"txn_no":"{txn_no}"}}'
        ),
    )
    db.add(event)
    await db.commit()

    return {
        "active_minutes": active_minutes,
        "charge_cents": charge_cents,
        "balance_after_cents": balance_after,
        "txn_no": txn_no,
    }


__all__ = [
    "add_message",
    "create_session",
    "end_session",
    "get_messages",
    "get_session",
    "update_active_seconds",
]
