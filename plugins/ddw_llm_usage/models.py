"""DDW LLM 用量中枢 — 数据模型与计费核心。

设计要点：
    * 金额一律用「分（int）」持久化，避开浮点误差；
    * 单价表用元/百万 token 表达，运行时通过 Decimal 换算为「分」；
    * 未知 model 走「同 provider 默认价」，并标记 pricing_defaulted=True。
"""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Pydantic 模型
# ---------------------------------------------------------------------------


class UsageRecord(BaseModel):
    """一次 LLM 调用的用量记录（持久化形态）。"""

    id: str = Field(..., description="调用方提供的 UUID，幂等键")
    ts: datetime = Field(..., description="调用时间（UTC）")
    plugin: str = Field(..., description="调用方插件名，如 ddw_wenqu_tutor")
    user: str = Field(..., description="用户标识（员工/学生）")
    model: str = Field(..., description="模型名")
    provider: str = Field(..., description="供应商（deepseek/minimax-cn/xiaomi/ollama）")  # noqa: E501
    input_tokens: int = Field(..., ge=0)
    output_tokens: int = Field(..., ge=0)
    cache_hit_tokens: int = Field(0, ge=0)
    cost_cents: int = Field(..., ge=0, description="本次调用费用，单位：分")
    session_id: Optional[str] = Field(None, description="关联会话 ID")
    pricing_defaulted: bool = Field(False, description="是否走了 provider 默认价（model 不在单价表）")  # noqa: E501


class UsageRecordIn(BaseModel):
    """POST /records 的请求体——费用服务端计算，调用方无需填。"""

    id: str
    ts: Optional[datetime] = None  # 缺省时取服务端 now(UTC)
    plugin: str
    user: str
    model: str
    provider: str
    input_tokens: int = Field(..., ge=0)
    output_tokens: int = Field(..., ge=0)
    cache_hit_tokens: int = Field(0, ge=0)
    session_id: Optional[str] = None

    @field_validator("plugin", "user", "model", "provider")
    @classmethod
    def _not_empty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("field must not be empty")
        return v


class ModelPrice(BaseModel):
    """单价表条目，单位：元 / 百万 token。"""

    model: str
    input_price: float = Field(..., ge=0)
    output_price: float = Field(..., ge=0)
    cache_hit_price: float = Field(0.0, ge=0)
    provider: Optional[str] = Field(None, description="冗余字段，便于按 provider 查找默认价")  # noqa: E501


class ModelPriceUpdate(BaseModel):
    """PUT /prices/{model} 的请求体。"""

    input_price: float = Field(..., ge=0)
    output_price: float = Field(..., ge=0)
    cache_hit_price: float = Field(0.0, ge=0)
    provider: Optional[str] = None


# ---------------------------------------------------------------------------
# 默认单价表（代码里写死，可被 PUT /prices/{model} 覆盖）
# ---------------------------------------------------------------------------
# 价格单位均为「元 / 百万 token」。官方价随手填的合理值，不是签约价：
#   - deepseek-v4-flash：与 DeepSeek V4 Flash 公价一致
#   - minimax-m3：       MiniMax-M3 标准档（按 token 计费，超低价段）
#   - mimo-v2.5-pro：    xiaomi MiMo 公开档
#   - qwen3.6:27b(本地)：本地模型不计费，照样记 token


DEFAULT_PRICES: dict[str, ModelPrice] = {
    "deepseek-v4-flash": ModelPrice(
        model="deepseek-v4-flash",
        input_price=1.0,
        output_price=2.0,
        cache_hit_price=0.02,
        provider="deepseek",
    ),
    "minimax-m3": ModelPrice(
        model="minimax-m3",
        input_price=0.30,
        output_price=0.30,
        cache_hit_price=0.03,
        provider="minimax-cn",
    ),
    "mimo-v2.5-pro": ModelPrice(
        model="mimo-v2.5-pro",
        input_price=3.2,
        output_price=9.6,
        cache_hit_price=0.96,
        provider="xiaomi",
    ),
    "qwen3.6:27b": ModelPrice(
        model="qwen3.6:27b",
        input_price=0.0,
        output_price=0.0,
        cache_hit_price=0.0,
        provider="ollama",
    ),
}

# 当 model 不在单价表时，按 provider 兜底的默认价（元/M）
# 取自同 provider 第一条「显式」配置；若 provider 也没显式配置，给保守的 deepseek 默认。
PROVIDER_FALLBACK_PRICES: dict[str, ModelPrice] = {
    p.provider: p for p in DEFAULT_PRICES.values() if p.provider
}


# ---------------------------------------------------------------------------
# 计费核心（Decimal 精确计算 → 分 int）
# ---------------------------------------------------------------------------

# 1 元 = 100 分；1 百万 token = 1_000_000 token
# cost_cents = (tokens * yuan_per_M) / 1_000_000 * 100 = tokens * yuan_per_M / 10_000
_YUAN_PER_M_TO_CENTS = Decimal(10000)


def _to_decimal(value: float) -> Decimal:
    """float → Decimal（用字符串路径，避免 float 隐误差直接进入 Decimal）。"""
    return Decimal(str(value))


def compute_cost_cents(
    *,
    input_tokens: int,
    output_tokens: int,
    cache_hit_tokens: int,
    input_price: float,
    output_price: float,
    cache_hit_price: float = 0.0,
) -> int:
    """按单价表（元/百万token）计算本次调用总费用，单位：分（int，半进位）。"""
    raw = (
        _to_decimal(input_tokens) * _to_decimal(input_price)
        + _to_decimal(output_tokens) * _to_decimal(output_price)
        + _to_decimal(cache_hit_tokens) * _to_decimal(cache_hit_price)
    )
    cents = (raw / _YUAN_PER_M_TO_CENTS).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(cents)


def resolve_price(
    model: str,
    provider: str,
    prices: Optional[dict[str, ModelPrice]] = None,
) -> tuple[ModelPrice, bool]:
    """查 model 单价；未命中则按 provider 兜底，返回 (price, pricing_defaulted)。"""
    table = prices if prices is not None else DEFAULT_PRICES
    hit = table.get(model)
    if hit is not None:
        return hit, False
    fb = PROVIDER_FALLBACK_PRICES.get(
        provider) or PROVIDER_FALLBACK_PRICES.get("deepseek")
    assert fb is not None  # 默认表一定至少有 deepseek
    # 用 provider 兜底价时，model 字段替换成实际调用方传的 model，便于审计
    return (
        ModelPrice(
            model=model,
            input_price=fb.input_price,
            output_price=fb.output_price,
            cache_hit_price=fb.cache_hit_price,
            provider=provider,
        ),
        True,
    )


def known_models() -> list[str]:
    """返回当前默认单价表里所有 model 名（供 /prices 接口与诊断用）。"""
    return list(DEFAULT_PRICES.keys())


__all__ = [
    "DEFAULT_PRICES",
    "PROVIDER_FALLBACK_PRICES",
    "ModelPrice",
    "ModelPriceUpdate",
    "UsageRecord",
    "UsageRecordIn",
    "compute_cost_cents",
    "known_models",
    "resolve_price",
]
