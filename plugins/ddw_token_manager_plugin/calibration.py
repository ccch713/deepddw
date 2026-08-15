"""
校准反算算法 — DDW 差异化核心

One API 没有此功能。DDW 需要基于 Provider 实际账单
反算校准系数 K，修正本地计费与 Provider 实际扣费的偏差。

校准流程:
1. 企业客户登记订阅信息（register_subscription）
2. 记录客户手动更新的实际用量（record_actual_usage）
3. 计算校准系数 K（calculate_calibration_ratio）
4. 判断是否已收敛（is_calibrated）
5. 低余额预警（alert_low_balance）

校准系数 K 的计算:
    K = sum(actual_costs) / sum(estimated_costs)
    当连续两次 K 变化 < 5% 时，视为收敛。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from .config_loader import get_ratio_loader
    from .models import CalibrationRecord, SubscriptionInfo
except ImportError:
    from models import CalibrationRecord, SubscriptionInfo

logger = logging.getLogger(__name__)

# ── 校准配置 ─────────────────────────────────────────────────────
DEFAULT_CALIBRATION_TOLERANCE = 0.05  # 5% 收敛阈值
ALERT_BALANCE_RATIO = 0.2  # 剩余 20% 时预警


@dataclass
class CalibrationStatus:
    """校准状态"""
    provider: str
    latest_k: float                       # 最新校准系数
    is_converged: bool                    # 是否已收敛
    consecutive_stable_count: int         # 连续稳定次数
    total_records: int                    # 总记录数
    estimated_total: float                # 累计估算费用
    actual_total: float                   # 累计实际费用
    alerts: list[str] = field(default_factory=list)  # 预警信息


@dataclass
class SubscriptionStatus:
    """订阅状态"""
    provider: str
    plan_name: str
    total_quota: float
    used_quota: float
    remaining: float
    usage_ratio: float
    is_active: bool
    expires_at: Optional[datetime]
    days_until_expiry: Optional[int]


async def register_subscription(
    session: AsyncSession,
    provider: str,
    plan_name: str,
    total_quota: float,
    expires_at: Optional[datetime] = None,
    notes: str = "",
) -> SubscriptionInfo:
    """
    企业客户登记订阅信息

    Args:
        session: 数据库会话
        provider: Provider 名称（如 'deepseek', 'openai', 'siliconflow'）
        plan_name: 订阅套餐名称
        total_quota: 总额度（美元或积分）
        expires_at: 到期时间
        notes: 备注

    Returns:
        新创建的 SubscriptionInfo
    """
    sub = SubscriptionInfo(
        provider=provider,
        plan_name=plan_name,
        total_quota=total_quota,
        expires_at=expires_at,
        notes=notes,
    )
    session.add(sub)
    await session.flush()
    logger.info(
        "登记订阅: provider=%s, plan=%s, quota=%.2f",
        provider, plan_name, total_quota,
    )
    return sub


async def record_actual_usage(
    session: AsyncSession,
    provider: str,
    actual_cost: float,
    estimated_cost: float,
    notes: str = "",
) -> CalibrationRecord:
    """
    记录客户手动更新的实际用量

    当客户从 Provider 后台获取实际扣费后，手动输入到系统。

    Args:
        session: 数据库会话
        provider: Provider 名称
        actual_cost: Provider 实际扣费（美元）
        estimated_cost: 本地估算费用（美元）
        notes: 备注

    Returns:
        新创建的 CalibrationRecord
    """
    # 计算单次校准系数
    k = actual_cost / estimated_cost if estimated_cost > 0 else 1.0

    record = CalibrationRecord(
        provider=provider,
        estimated_cost=estimated_cost,
        actual_cost=actual_cost,
        ratio_adjustment=k,
        notes=notes,
    )
    session.add(record)
    await session.flush()
    logger.info(
        "记录实际用量: provider=%s, estimated=%.4f, actual=%.4f, K=%.4f",
        provider, estimated_cost, actual_cost, k,
    )
    return record


async def calculate_calibration_ratio(
    session: AsyncSession,
    provider: str,
    lookback_days: int = 30,
) -> CalibrationStatus:
    """
    计算校准系数 K

    K = sum(actual_costs) / sum(estimated_costs)

    Args:
        session: 数据库会话
        provider: Provider 名称
        lookback_days: 回溯天数

    Returns:
        CalibrationStatus
    """
    cutoff = datetime.now() - timedelta(days=lookback_days)

    # 查询指定 Provider 的校准记录
    result = await session.execute(
        select(CalibrationRecord)
        .where(CalibrationRecord.provider == provider)
        .where(CalibrationRecord.created_at >= cutoff)
        .order_by(CalibrationRecord.created_at.desc())
    )
    records = result.scalars().all()

    if not records:
        return CalibrationStatus(
            provider=provider,
            latest_k=1.0,
            is_converged=False,
            consecutive_stable_count=0,
            total_records=0,
            estimated_total=0.0,
            actual_total=0.0,
        )

    estimated_total = sum(r.estimated_cost for r in records)
    actual_total = sum(r.actual_cost for r in records)

    # 计算综合 K
    latest_k = actual_total / estimated_total if estimated_total > 0 else 1.0

    # 检查是否收敛（连续两次 K 变化 < tolerance）
    is_converged, stable_count = _check_convergence(records, DEFAULT_CALIBRATION_TOLERANCE)

    # 检查低余额预警
    alerts = await _check_low_balance_alerts(session, provider)

    status = CalibrationStatus(
        provider=provider,
        latest_k=latest_k,
        is_converged=is_converged,
        consecutive_stable_count=stable_count,
        total_records=len(records),
        estimated_total=estimated_total,
        actual_total=actual_total,
        alerts=alerts,
    )

    logger.info(
        "校准系数: provider=%s, K=%.4f, converged=%s, records=%d",
        provider, latest_k, is_converged, len(records),
    )
    return status


async def is_calibrated(
    session: AsyncSession,
    provider: str,
    tolerance: float = DEFAULT_CALIBRATION_TOLERANCE,
    min_records: int = 2,
) -> bool:
    """
    判断该 Provider 是否已校准收敛

    收敛条件: 连续两次 K 变化 < tolerance

    Args:
        session: 数据库会话
        provider: Provider 名称
        tolerance: 收敛容忍度
        min_records: 最少记录数

    Returns:
        是否已收敛
    """
    result = await session.execute(
        select(CalibrationRecord)
        .where(CalibrationRecord.provider == provider)
        .order_by(CalibrationRecord.created_at.desc())
        .limit(10)  # 只看最近 10 条
    )
    records = result.scalars().all()

    if len(records) < min_records:
        return False

    is_converged, _ = _check_convergence(records, tolerance)
    return is_converged


async def alert_low_balance(
    session: AsyncSession,
    provider: str,
    alert_threshold: float = ALERT_BALANCE_RATIO,
) -> list[str]:
    """
    低余额预警

    当订阅剩余额度低于总额度的 alert_threshold 时发出预警。

    Args:
        session: 数据库会话
        provider: Provider 名称
        alert_threshold: 预警阈值（0.0 ~ 1.0）

    Returns:
        预警信息列表
    """
    return await _check_low_balance_alerts(session, provider, alert_threshold)


async def get_subscription_status(
    session: AsyncSession,
    provider: str,
) -> Optional[SubscriptionStatus]:
    """
    获取订阅状态

    Args:
        session: 数据库会话
        provider: Provider 名称

    Returns:
        SubscriptionStatus 或 None
    """
    result = await session.execute(
        select(SubscriptionInfo)
        .where(SubscriptionInfo.provider == provider)
        .where(SubscriptionInfo.is_active == True)
        .order_by(SubscriptionInfo.created_at.desc())
        .limit(1)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return None

    days_until_expiry = None
    if sub.expires_at:
        delta = sub.expires_at - datetime.now()
        days_until_expiry = max(delta.days, 0)

    return SubscriptionStatus(
        provider=sub.provider,
        plan_name=sub.plan_name,
        total_quota=sub.total_quota,
        used_quota=sub.used_quota,
        remaining=sub.remaining,
        usage_ratio=sub.usage_ratio,
        is_active=sub.is_active,
        expires_at=sub.expires_at,
        days_until_expiry=days_until_expiry,
    )


# ── 内部辅助函数 ────────────────────────────────────────────────


def _check_convergence(
    records: list[CalibrationRecord],
    tolerance: float,
) -> tuple[bool, int]:
    """
    检查校准系数是否收敛

    收敛条件: 连续两次 K 变化 < tolerance

    Returns:
        (is_converged, consecutive_stable_count)
    """
    if len(records) < 2:
        return False, 0

    # 按时间正序排列（records 可能是倒序的）
    sorted_records = sorted(records, key=lambda r: r.created_at)

    stable_count = 0
    for i in range(len(sorted_records) - 1, 0, -1):
        current_k = sorted_records[i].ratio_adjustment
        prev_k = sorted_records[i - 1].ratio_adjustment

        if prev_k == 0:
            break

        change = abs(current_k - prev_k) / prev_k
        if change < tolerance:
            stable_count += 1
        else:
            break

    return stable_count >= 1, stable_count


async def _check_low_balance_alerts(
    session: AsyncSession,
    provider: str,
    threshold: float = ALERT_BALANCE_RATIO,
) -> list[str]:
    """检查低余额预警"""
    alerts = []
    result = await session.execute(
        select(SubscriptionInfo)
        .where(SubscriptionInfo.provider == provider)
        .where(SubscriptionInfo.is_active == True)
    )
    subs = result.scalars().all()

    for sub in subs:
        if sub.total_quota > 0 and sub.usage_ratio > (1.0 - threshold):
            alerts.append(
                f"[预警] {provider}/{sub.plan_name} "
                f"剩余额度 {sub.remaining:.2f} ({sub.usage_ratio:.1%} 已用)"
            )
        if sub.expires_at and sub.expires_at < datetime.now() + timedelta(days=7):
            days_left = (sub.expires_at - datetime.now()).days
            alerts.append(
                f"[预警] {provider}/{sub.plan_name} "
                f"将在 {days_left} 天后到期"
            )

    return alerts
