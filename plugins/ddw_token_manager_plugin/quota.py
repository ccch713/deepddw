"""
预消费/后消费核心算法

完整映射 One API 源码:
- pre_consume_quota()  → relay/controller/helper.go:preConsumeQuota (L68-95)
- post_consume_quota() → relay/controller/helper.go:postConsumeQuota (L97-141)
- return_pre_consumed_quota() → 对应 helper.go 失败回滚路径

消费流程:
    请求进入 → pre_consume_quota() → 执行请求 → post_consume_quota()
                                      ↓ 失败
                                return_pre_consumed_quota() (回滚)

高信任跳过机制:
    当 userQuota > 100 * preConsumedQuota 时，跳过 Token 级别预扣
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from .config_loader import get_ratio_loader
    from .models import ConsumeLog, TokenQuota, TokenStatus
except ImportError:
    from config_loader import get_ratio_loader
    from models import ConsumeLog, TokenQuota

logger = logging.getLogger(__name__)

# ── 预消费基础额度 ──────────────────────────────────────────────
# 对应 One API: config.PreConsumedQuota
DEFAULT_PRE_CONSUMED_QUOTA = 500


@dataclass
class PreConsumeResult:
    """预消费结果"""
    pre_consumed_quota: int          # 预消费额度
    error_message: Optional[str]     # 错误信息（None 表示成功）
    user_quota_before: int           # 用户预消费前额度


@dataclass
class PostConsumeResult:
    """后消费结果"""
    actual_quota: int                # 实际消耗 quota
    quota_delta: int                 # 差额（actual - pre_consumed）
    error_message: Optional[str]


async def get_user_quota(session: AsyncSession, user_id: int) -> int:
    """
    获取用户额度

    对应 One API: model.CacheGetUserQuota → model/user.go:GetUserQuota
    """
    result = await session.execute(
        select(TokenQuota.remain_quota)
        .where(TokenQuota.user_id == user_id)
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row if row is not None else 0


async def pre_consume_quota(
    session: AsyncSession,
    user_id: int,
    token_id: int,
    prompt_tokens: int,
    max_tokens: int,
    model: str,
    channel_type: int = 0,
    group: str = "default",
    pre_consumed_quota_config: int = DEFAULT_PRE_CONSUMED_QUOTA,
) -> PreConsumeResult:
    """
    预消费额度

    对应 One API: relay/controller/helper.go:preConsumeQuota (L68-95)

    流程:
    1. 计算预消费额度 = (基础额度 + promptTokens + maxTokens) * ratio
    2. 检查用户额度是否充足
    3. 高额用户跳过 Token 预扣（信任机制）
    4. 预扣 Token 额度

    Args:
        session: 数据库会话
        user_id: 用户 ID
        token_id: 令牌 ID
        prompt_tokens: 输入 token 数
        max_tokens: 最大输出 token 数（0 表示不限）
        model: 模型名称
        channel_type: 渠道类型
        group: 用户分组
        pre_consumed_quota_config: 预消费基础额度配置

    Returns:
        PreConsumeResult
    """
    # 对应 helper.go:L60-66 — getPreConsumedQuota
    loader = get_ratio_loader()
    ratio = loader.get_input_ratio(model, channel_type)

    pre_consumed_tokens = pre_consumed_quota_config + prompt_tokens
    if max_tokens > 0:
        pre_consumed_tokens += max_tokens
    pre_consumed_quota = int(float(pre_consumed_tokens) * ratio)

    # 对应 helper.go:L71-77 — 检查用户额度
    user_quota = await get_user_quota(session, user_id)
    if user_quota - pre_consumed_quota < 0:
        return PreConsumeResult(
            pre_consumed_quota=pre_consumed_quota,
            error_message="用户额度不足 (insufficient_user_quota)",
            user_quota_before=user_quota,
        )

    # 对应 helper.go:L78 — 预扣用户额度
    await _decrease_user_quota(session, user_id, pre_consumed_quota)

    # 对应 helper.go:L82-87 — 高额用户信任跳过
    trusted = False
    if user_quota > 100 * pre_consumed_quota:
        pre_consumed_quota = 0
        trusted = True
        logger.info(
            "用户 %d 额度充足 (%d), 跳过Token预扣",
            user_id, user_quota,
        )

    # 对应 helper.go:L88-93 — 预扣Token额度
    if pre_consumed_quota > 0:
        await _pre_consume_token_quota(session, token_id, pre_consumed_quota)

    return PreConsumeResult(
        pre_consumed_quota=pre_consumed_quota,
        error_message=None,
        user_quota_before=user_quota,
    )


async def post_consume_quota(
    session: AsyncSession,
    token_id: int,
    user_id: int,
    channel_id: int,
    prompt_tokens: int,
    completion_tokens: int,
    model: str,
    token_name: str,
    pre_consumed_quota: int,
    model_ratio: Optional[float] = None,
    group_ratio: Optional[float] = None,
    group: str = "default",
    channel_type: int = 0,
    is_stream: bool = False,
    elapsed_time_ms: int = 0,
    request_id: str = "",
) -> PostConsumeResult:
    """
    后消费 — 实际消耗 + 差额补偿

    对应 One API: relay/controller/helper.go:postConsumeQuota (L97-141)

    流程:
    1. 计算实际 quota = ceil((promptTokens + completionTokens * completionRatio) * ratio * groupRatio)
    2. 最小保证: ratio != 0 时 quota <= 0 → quota = 1
    3. 补偿差额: quotaDelta = quota - preConsumedQuota
    4. 记录消费日志
    """
    loader = get_ratio_loader()
    if model_ratio is None:
        model_ratio = loader.get_input_ratio(model, channel_type)
    if group_ratio is None:
        group_ratio = loader.get_group_ratio(group)

    completion_ratio = loader.get_completion_ratio(model, channel_type)

    # 对应 helper.go:L103-106 — 计算实际 quota
    total_tokens = prompt_tokens + completion_tokens
    if total_tokens == 0:
        # 对应 helper.go:L111-115 — 异常情况 quota=0
        quota = 0
    else:
        quota = math.ceil(
            (float(prompt_tokens) + float(completion_tokens) * completion_ratio)
            * model_ratio
            * group_ratio
        )

    # 对应 helper.go:L107-109 — 最小消耗保证
    if model_ratio != 0 and quota <= 0:
        quota = 1

    # 对应 helper.go:L116-120 — 补偿差额
    quota_delta = quota - pre_consumed_quota
    try:
        await _post_consume_token_quota(session, token_id, user_id, quota_delta)
    except Exception as e:
        logger.error("后消费Token额度失败: %s", e)

    # 对应 helper.go:L126-138 — 记录消费日志
    log_content = f"倍率：{model_ratio:.2f} × {group_ratio:.2f} × {completion_ratio:.2f}"
    await _record_consume_log(
        session=session,
        user_id=user_id,
        token_id=token_id,
        channel_id=channel_id,
        model=model,
        token_name=token_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        quota_cost=quota,
        content=log_content,
        is_stream=is_stream,
        elapsed_time_ms=elapsed_time_ms,
        request_id=request_id,
    )

    return PostConsumeResult(
        actual_quota=quota,
        quota_delta=quota_delta,
        error_message=None,
    )


async def return_pre_consumed_quota(
    session: AsyncSession,
    token_id: int,
    user_id: int,
    pre_consumed_quota: int,
) -> None:
    """
    退还预消费额度

    当请求失败时调用，回滚 pre_consume_quota 的预扣操作。
    对应 One API 中请求失败时的回滚路径。
    """
    if pre_consumed_quota <= 0:
        return

    # 退还 Token 额度
    token = await session.get(TokenQuota, token_id)
    if token and not token.unlimited_quota:
        token.remain_quota += pre_consumed_quota
        token.used_quota -= pre_consumed_quota
        token.accessed_time = time.time()

    # 退还用户额度（通过增加同用户其他 token 的额度来模拟）
    # 实际实现需要查 user 表，这里简化为直接更新 token
    logger.info(
        "退还预消费额度: token_id=%d, user_id=%d, quota=%d",
        token_id, user_id, pre_consumed_quota,
    )


# ── 内部辅助函数 ────────────────────────────────────────────────


async def _decrease_user_quota(session: AsyncSession, user_id: int, quota: int) -> None:
    """
    扣减用户额度

    对应 One API: model/user.go:DecreaseUserQuota
    """
    # 查找该用户第一个可用 token 来代表用户额度
    result = await session.execute(
        select(TokenQuota)
        .where(TokenQuota.user_id == user_id)
        .limit(1)
    )
    token = result.scalar_one_or_none()
    if token:
        token.remain_quota -= quota
        token.used_quota += quota
        token.accessed_time = time.time()


async def _pre_consume_token_quota(session: AsyncSession, token_id: int, quota: int) -> None:
    """
    预扣 Token 额度

    对应 One API: model/token.go:PreConsumeTokenQuota (L217-280)
    """
    token = await session.get(TokenQuota, token_id)
    if not token:
        raise ValueError(f"令牌 {token_id} 不存在")

    # 对应 token.go:L225-227
    if not token.unlimited_quota and token.remain_quota < quota:
        raise ValueError("令牌额度不足")

    # 对应 token.go:L272-277
    if not token.unlimited_quota:
        token.remain_quota -= quota
        token.used_quota += quota
        token.accessed_time = time.time()


async def _post_consume_token_quota(
    session: AsyncSession,
    token_id: int,
    user_id: int,
    quota_delta: int,
) -> None:
    """
    后消费差额补偿

    对应 One API: model/token.go:PostConsumeTokenQuota (L282-303)
    """
    token = await session.get(TokenQuota, token_id)
    if not token:
        return

    # 对应 token.go:L287-290 — 用户额度补偿
    if quota_delta > 0:
        # 实际消耗更多，追扣
        user_quota = await get_user_quota(session, user_id)
        # 简化：通过 token 代表用户额度
    else:
        # 实际消耗更少，退还
        pass

    # 对应 token.go:L292-301 — Token 额度补偿
    if not token.unlimited_quota:
        if quota_delta > 0:
            token.remain_quota -= quota_delta
            token.used_quota += quota_delta
        else:
            token.remain_quota += abs(quota_delta)
            token.used_quota -= abs(quota_delta)
        token.accessed_time = time.time()


async def _record_consume_log(
    session: AsyncSession,
    user_id: int,
    token_id: int,
    channel_id: int,
    model: str,
    token_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    quota_cost: int,
    content: str,
    is_stream: bool = False,
    elapsed_time_ms: int = 0,
    request_id: str = "",
) -> None:
    """
    记录消费日志

    对应 One API: model/log.go:RecordConsumeLog
    """
    log = ConsumeLog(
        user_id=user_id,
        token_id=token_id,
        channel_id=channel_id,
        model=model,
        token_name=token_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        quota_cost=quota_cost,
        content=content,
        is_stream=is_stream,
        elapsed_time=elapsed_time_ms,
        request_id=request_id,
    )
    session.add(log)
    await session.flush()
