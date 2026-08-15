"""用量计费（2026-08-14 M0-5）。

计费模型（用户拍板）：token 消耗量 × 单价 + OCR/TTS 用量 × 单价，
单会话 45 分钟封顶 25 元，超限写消费警示记录（防"乱收费"法律风险）。

费率：
- 推理 token = DeepSeek 涨价后单价 × 4（输入 800 分/百万、输出 3200 分/百万）
- OCR = MiniMax 定价 × 3（0.2 元/张，M0-7 OCR 管线激活后生效）
- TTS = MiniMax 定价 × 3（0.15 元/千字，占位）

token 计量：本地估算（CJK=1 / 非CJK=0.25），消息入库时写入 token_count；
LLM 走底座 gateway 后可升级为真实 usage（M0-6）。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wenqu_tutor.config import (
    BILLING_CAP_CENTS,
    OCR_PRICE_CENTS_PER_PAGE,
    TOKEN_PRICE_IN_CENTS_PER_MILLION,
    TOKEN_PRICE_OUT_CENTS_PER_MILLION,
    TTS_PRICE_CENTS_PER_1K_CHAR,
)
from plugins.ddw_wenqu_tutor.models import (
    WenquMessage,
    WenquStudyEvent,
)
from plugins.ddw_wenqu_tutor.prompt.token_budget import (
    estimate_tokens,
)

# 单会话最低扣费（分），防零元会话刷审计
MIN_CHARGE_CENTS = 1


def estimate_usage_cents(
    in_tokens: int,
    out_tokens: int,
    ocr_pages: int = 0,
    tts_chars: int = 0,
) -> int:
    """按用量 × 单价计算费用（分）。"""
    return (
        in_tokens * TOKEN_PRICE_IN_CENTS_PER_MILLION // 1_000_000
        + out_tokens * TOKEN_PRICE_OUT_CENTS_PER_MILLION // 1_000_000
        + ocr_pages * OCR_PRICE_CENTS_PER_PAGE
        + tts_chars * TTS_PRICE_CENTS_PER_1K_CHAR // 1000
    )


async def collect_session_tokens(
    db: AsyncSession,
    session_id: str,
) -> tuple[int, int]:
    """聚合会话消息 token：assistant=输出，其余（system/user）=输入。"""
    result = await db.execute(
        select(WenquMessage).where(
            WenquMessage.session_id == session_id
        )
    )
    messages = result.scalars().all()
    in_tokens = 0
    out_tokens = 0
    for m in messages:
        t = m.token_count or estimate_tokens(m.content or "")
        if m.role == "assistant":
            out_tokens += t
        else:
            in_tokens += t
    return in_tokens, out_tokens


async def settle_usage(
    db: AsyncSession,
    session_id: str,
    ocr_pages: int = 0,
    tts_chars: int = 0,
) -> dict:
    """结算用量 → 封顶 → 超限写警示记录。

    Returns:
        dict: in_tokens / out_tokens / usage_cents /
              capped / charge_cents
    """
    in_tokens, out_tokens = await collect_session_tokens(
        db, session_id
    )
    usage_cents = estimate_usage_cents(
        in_tokens, out_tokens, ocr_pages, tts_chars
    )
    capped = usage_cents > BILLING_CAP_CENTS
    charge_cents = min(usage_cents, BILLING_CAP_CENTS)
    if charge_cents < MIN_CHARGE_CENTS:
        charge_cents = MIN_CHARGE_CENTS

    if capped:
        # 消费警示记录（审计留痕，防乱收费纠纷）
        db.add(
            WenquStudyEvent(
                session_id=session_id,
                event_type="billing_cap_warning",
                payload=(
                    f'{{"usage_cents":{usage_cents},'
                    f'"cap_cents":{BILLING_CAP_CENTS}}}'
                ),
            )
        )
        await db.commit()

    return {
        "in_tokens": in_tokens,
        "out_tokens": out_tokens,
        "usage_cents": usage_cents,
        "capped": capped,
        "charge_cents": charge_cents,
    }


__all__ = [
    "MIN_CHARGE_CENTS",
    "collect_session_tokens",
    "estimate_usage_cents",
    "settle_usage",
]
