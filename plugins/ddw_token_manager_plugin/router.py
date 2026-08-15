"""
FastAPI 路由 — Token 额度管理 API

所有路由以 /api/v1/plugins/ddw-token-manager 为前缀挂载。

路由清单:
- POST /api/quota/pre-consume    — 预消费
- POST /api/quota/post-consume   — 后消费
- POST /api/quota/return         — 退还
- GET  /api/quota/balance/{uid}  — 查询余额
- POST /api/calibration/register — 登记订阅
- POST /api/calibration/update   — 更新实际用量
- GET  /api/calibration/status/{provider} — 校准状态
- GET  /api/cost/realtime        — 实时成本
- GET  /api/cost/daily           — 日成本统计
- GET  /api/cost/by-model        — 按模型统计
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from .calibration import (
        CalibrationStatus,
        alert_low_balance,
        calculate_calibration_ratio,
        get_subscription_status,
        record_actual_usage,
        register_subscription,
    )
    from .config_loader import get_ratio_loader
    from .models import CalibrationRecord, ConsumeLog, SubscriptionInfo, TokenQuota
    from .quota import (
        PreConsumeResult,
        post_consume_quota,
        pre_consume_quota,
        return_pre_consumed_quota,
    )
except ImportError:
    from calibration import (
        calculate_calibration_ratio,
        record_actual_usage,
        register_subscription,
    )
    from config_loader import get_ratio_loader
    from models import ConsumeLog, TokenQuota
    from quota import (
        post_consume_quota,
        pre_consume_quota,
        return_pre_consumed_quota,
    )

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Pydantic 请求/响应模型 ──────────────────────────────────────


class PreConsumeRequest(BaseModel):
    """预消费请求"""
    user_id: int = Field(..., description="用户 ID")
    token_id: int = Field(..., description="令牌 ID")
    prompt_tokens: int = Field(..., ge=0, description="输入 token 数")
    max_tokens: int = Field(0, ge=0, description="最大输出 token 数")
    model: str = Field(..., description="模型名称")
    channel_type: int = Field(0, description="渠道类型")
    group: str = Field("default", description="用户分组")


class PreConsumeResponse(BaseModel):
    """预消费响应"""
    success: bool
    pre_consumed_quota: int
    error_message: Optional[str] = None
    user_quota_before: int


class PostConsumeRequest(BaseModel):
    """后消费请求"""
    token_id: int = Field(..., description="令牌 ID")
    user_id: int = Field(..., description="用户 ID")
    channel_id: int = Field(0, description="渠道 ID")
    prompt_tokens: int = Field(..., ge=0, description="输入 token 数")
    completion_tokens: int = Field(..., ge=0, description="输出 token 数")
    model: str = Field(..., description="模型名称")
    token_name: str = Field("", description="令牌名称")
    pre_consumed_quota: int = Field(0, description="预消费额度")
    group: str = Field("default", description="用户分组")
    channel_type: int = Field(0, description="渠道类型")
    is_stream: bool = Field(False, description="是否流式请求")
    elapsed_time_ms: int = Field(0, description="耗时（毫秒）")
    request_id: str = Field("", description="请求 ID")


class PostConsumeResponse(BaseModel):
    """后消费响应"""
    success: bool
    actual_quota: int
    quota_delta: int
    error_message: Optional[str] = None


class ReturnRequest(BaseModel):
    """退还请求"""
    token_id: int = Field(..., description="令牌 ID")
    user_id: int = Field(..., description="用户 ID")
    pre_consumed_quota: int = Field(..., ge=0, description="预消费额度")


class BalanceResponse(BaseModel):
    """余额响应"""
    user_id: int
    token_id: Optional[int] = None
    remain_quota: int
    used_quota: int
    unlimited_quota: bool


class RegisterSubscriptionRequest(BaseModel):
    """登记订阅请求"""
    provider: str = Field(..., description="Provider 名称")
    plan_name: str = Field(..., description="订阅套餐名称")
    total_quota: float = Field(..., gt=0, description="总额度")
    expires_at: Optional[datetime] = Field(None, description="到期时间")
    notes: str = Field("", description="备注")


class UpdateUsageRequest(BaseModel):
    """更新实际用量请求"""
    provider: str = Field(..., description="Provider 名称")
    actual_cost: float = Field(..., ge=0, description="实际扣费（美元）")
    estimated_cost: float = Field(..., ge=0, description="本地估算费用（美元）")
    notes: str = Field("", description="备注")


class CalibrationStatusResponse(BaseModel):
    """校准状态响应"""
    provider: str
    latest_k: float
    is_converged: bool
    consecutive_stable_count: int
    total_records: int
    estimated_total: float
    actual_total: float
    alerts: list[str] = []


class CostSummaryResponse(BaseModel):
    """成本统计响应"""
    total_quota: int
    total_prompt_tokens: int
    total_completion_tokens: int
    request_count: int


class ModelCostResponse(BaseModel):
    """按模型统计响应"""
    model: str
    total_quota: int
    total_prompt_tokens: int
    total_completion_tokens: int
    request_count: int


# ── 数据库会话依赖（由主应用提供）───────────────────────────────
# 这里使用占位符，实际由 FastAPI Depends 注入
_db_session_factory = None


def set_db_session_factory(factory):
    """设置数据库会话工厂（由 main.py 调用）"""
    global _db_session_factory
    _db_session_factory = factory


async def get_db() -> AsyncSession:
    """获取数据库会话"""
    if _db_session_factory is None:
        raise HTTPException(500, "数据库未初始化")
    async with _db_session_factory() as session:
        yield session


# ── 额度管理路由 ─────────────────────────────────────────────────


@router.post("/quota/pre-consume", response_model=PreConsumeResponse)
async def api_pre_consume(
    req: PreConsumeRequest,
    session: AsyncSession = Depends(get_db),
):
    """
    预消费额度

    对应 One API: relay/controller/helper.go:preConsumeQuota (L68-95)
    """
    try:
        result = await pre_consume_quota(
            session=session,
            user_id=req.user_id,
            token_id=req.token_id,
            prompt_tokens=req.prompt_tokens,
            max_tokens=req.max_tokens,
            model=req.model,
            channel_type=req.channel_type,
            group=req.group,
        )
        await session.commit()
        return PreConsumeResponse(
            success=result.error_message is None,
            pre_consumed_quota=result.pre_consumed_quota,
            error_message=result.error_message,
            user_quota_before=result.user_quota_before,
        )
    except Exception as e:
        logger.error("预消费失败: %s", e)
        await session.rollback()
        raise HTTPException(500, f"预消费失败: {e}")


@router.post("/quota/post-consume", response_model=PostConsumeResponse)
async def api_post_consume(
    req: PostConsumeRequest,
    session: AsyncSession = Depends(get_db),
):
    """
    后消费 — 实际消耗 + 差额补偿

    对应 One API: relay/controller/helper.go:postConsumeQuota (L97-141)
    """
    try:
        result = await post_consume_quota(
            session=session,
            token_id=req.token_id,
            user_id=req.user_id,
            channel_id=req.channel_id,
            prompt_tokens=req.prompt_tokens,
            completion_tokens=req.completion_tokens,
            model=req.model,
            token_name=req.token_name,
            pre_consumed_quota=req.pre_consumed_quota,
            group=req.group,
            channel_type=req.channel_type,
            is_stream=req.is_stream,
            elapsed_time_ms=req.elapsed_time_ms,
            request_id=req.request_id,
        )
        await session.commit()
        return PostConsumeResponse(
            success=True,
            actual_quota=result.actual_quota,
            quota_delta=result.quota_delta,
        )
    except Exception as e:
        logger.error("后消费失败: %s", e)
        await session.rollback()
        raise HTTPException(500, f"后消费失败: {e}")


@router.post("/quota/return")
async def api_return_quota(
    req: ReturnRequest,
    session: AsyncSession = Depends(get_db),
):
    """
    退还预消费额度

    当请求失败时调用，回滚预扣操作。
    """
    try:
        await return_pre_consumed_quota(
            session=session,
            token_id=req.token_id,
            user_id=req.user_id,
            pre_consumed_quota=req.pre_consumed_quota,
        )
        await session.commit()
        return {"success": True, "message": "额度已退还"}
    except Exception as e:
        logger.error("退还失败: %s", e)
        await session.rollback()
        raise HTTPException(500, f"退还失败: {e}")


@router.get("/quota/balance/{user_id}", response_model=list[BalanceResponse])
async def api_get_balance(
    user_id: int,
    session: AsyncSession = Depends(get_db),
):
    """
    查询用户所有令牌余额
    """
    result = await session.execute(
        select(TokenQuota).where(TokenQuota.user_id == user_id)
    )
    tokens = result.scalars().all()
    return [
        BalanceResponse(
            user_id=t.user_id,
            token_id=t.id,
            remain_quota=t.remain_quota,
            used_quota=t.used_quota,
            unlimited_quota=t.unlimited_quota,
        )
        for t in tokens
    ]


# ── 校准管理路由 ─────────────────────────────────────────────────


@router.post("/calibration/register")
async def api_register_subscription(
    req: RegisterSubscriptionRequest,
    session: AsyncSession = Depends(get_db),
):
    """
    登记订阅信息
    """
    try:
        sub = await register_subscription(
            session=session,
            provider=req.provider,
            plan_name=req.plan_name,
            total_quota=req.total_quota,
            expires_at=req.expires_at,
            notes=req.notes,
        )
        await session.commit()
        return {"success": True, "subscription_id": sub.id}
    except Exception as e:
        logger.error("登记订阅失败: %s", e)
        await session.rollback()
        raise HTTPException(500, f"登记失败: {e}")


@router.post("/calibration/update")
async def api_update_usage(
    req: UpdateUsageRequest,
    session: AsyncSession = Depends(get_db),
):
    """
    更新实际用量
    """
    try:
        record = await record_actual_usage(
            session=session,
            provider=req.provider,
            actual_cost=req.actual_cost,
            estimated_cost=req.estimated_cost,
            notes=req.notes,
        )
        await session.commit()
        return {"success": True, "record_id": record.id, "k": record.ratio_adjustment}
    except Exception as e:
        logger.error("更新用量失败: %s", e)
        await session.rollback()
        raise HTTPException(500, f"更新失败: {e}")


@router.get("/calibration/status/{provider}", response_model=CalibrationStatusResponse)
async def api_calibration_status(
    provider: str,
    lookback_days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_db),
):
    """
    获取校准状态
    """
    status = await calculate_calibration_ratio(
        session=session,
        provider=provider,
        lookback_days=lookback_days,
    )
    return CalibrationStatusResponse(
        provider=status.provider,
        latest_k=status.latest_k,
        is_converged=status.is_converged,
        consecutive_stable_count=status.consecutive_stable_count,
        total_records=status.total_records,
        estimated_total=status.estimated_total,
        actual_total=status.actual_total,
        alerts=status.alerts,
    )


# ── 成本统计路由 ─────────────────────────────────────────────────


@router.get("/cost/realtime", response_model=CostSummaryResponse)
async def api_realtime_cost(
    minutes: int = Query(5, ge=1, le=60, description="最近N分钟"),
    session: AsyncSession = Depends(get_db),
):
    """
    实时成本查询 — 最近 N 分钟的消费统计
    """
    cutoff = datetime.now() - timedelta(minutes=minutes)
    result = await session.execute(
        select(
            func.coalesce(func.sum(ConsumeLog.quota_cost), 0),
            func.coalesce(func.sum(ConsumeLog.prompt_tokens), 0),
            func.coalesce(func.sum(ConsumeLog.completion_tokens), 0),
            func.count(ConsumeLog.id),
        ).where(ConsumeLog.created_at >= cutoff)
    )
    row = result.one()
    return CostSummaryResponse(
        total_quota=int(row[0]),
        total_prompt_tokens=int(row[1]),
        total_completion_tokens=int(row[2]),
        request_count=int(row[3]),
    )


@router.get("/cost/daily", response_model=CostSummaryResponse)
async def api_daily_cost(
    date: Optional[str] = Query(None, description="日期 YYYY-MM-DD，默认今天"),
    session: AsyncSession = Depends(get_db),
):
    """
    日成本统计
    """
    if date:
        target_date = datetime.strptime(date, "%Y-%m-%d")
    else:
        target_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    next_date = target_date + timedelta(days=1)
    result = await session.execute(
        select(
            func.coalesce(func.sum(ConsumeLog.quota_cost), 0),
            func.coalesce(func.sum(ConsumeLog.prompt_tokens), 0),
            func.coalesce(func.sum(ConsumeLog.completion_tokens), 0),
            func.count(ConsumeLog.id),
        ).where(
            ConsumeLog.created_at >= target_date,
            ConsumeLog.created_at < next_date,
        )
    )
    row = result.one()
    return CostSummaryResponse(
        total_quota=int(row[0]),
        total_prompt_tokens=int(row[1]),
        total_completion_tokens=int(row[2]),
        request_count=int(row[3]),
    )


@router.get("/cost/by-model", response_model=list[ModelCostResponse])
async def api_cost_by_model(
    days: int = Query(7, ge=1, le=90, description="最近N天"),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
):
    """
    按模型统计成本
    """
    cutoff = datetime.now() - timedelta(days=days)
    result = await session.execute(
        select(
            ConsumeLog.model,
            func.coalesce(func.sum(ConsumeLog.quota_cost), 0).label("total_quota"),
            func.coalesce(func.sum(ConsumeLog.prompt_tokens), 0).label("total_prompt"),
            func.coalesce(func.sum(ConsumeLog.completion_tokens), 0).label("total_completion"),
            func.count(ConsumeLog.id).label("request_count"),
        )
        .where(ConsumeLog.created_at >= cutoff)
        .group_by(ConsumeLog.model)
        .order_by(func.sum(ConsumeLog.quota_cost).desc())
        .limit(limit)
    )
    rows = result.all()
    return [
        ModelCostResponse(
            model=row[0],
            total_quota=int(row[1]),
            total_prompt_tokens=int(row[2]),
            total_completion_tokens=int(row[3]),
            request_count=int(row[4]),
        )
        for row in rows
    ]


# ── 倍率查询路由 ─────────────────────────────────────────────────


@router.get("/ratio/model/{model_name}")
async def api_get_model_ratio(model_name: str):
    """
    查询模型倍率
    """
    loader = get_ratio_loader()
    return {
        "model": model_name,
        "input_ratio": loader.get_input_ratio(model_name),
        "completion_ratio": loader.get_completion_ratio(model_name),
    }


@router.get("/ratio/group/{group_name}")
async def api_get_group_ratio(group_name: str):
    """
    查询分组倍率
    """
    loader = get_ratio_loader()
    return {
        "group": group_name,
        "ratio": loader.get_group_ratio(group_name),
    }


@router.get("/ratio/models")
async def api_list_models():
    """
    列出所有已配置的模型
    """
    loader = get_ratio_loader()
    return {
        "count": loader.get_model_count(),
        "models": loader.get_all_models(),
    }


# ── 健康检查 ─────────────────────────────────────────────────────


@router.get("/health")
async def api_health():
    """插件健康检查"""
    loader = get_ratio_loader()
    return {
        "plugin": "ddw-token-manager",
        "status": "ok",
        "model_count": loader.get_model_count(),
    }
