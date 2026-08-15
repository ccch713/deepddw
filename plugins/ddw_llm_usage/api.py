"""DDW LLM 用量中枢 — FastAPI 路由层。

所有路由挂到 Plugin 父类预创建的 ``self.router`` 上（带 prefix
``/api/v1/plugins/ddw_llm_usage``），由 ``plugin.Plugin.setup()`` 调
``register_routes(router, plugin)`` 完成。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from pydantic import BaseModel, Field

from .models import ModelPrice, ModelPriceUpdate, UsageRecord, UsageRecordIn
from .storage import UsageStorage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 鉴权依赖
# ---------------------------------------------------------------------------


def require_admin_key(x_admin_key: str | None = Header(default=None)) -> None:
    """校验 X-Admin-Key header，用于 PUT/DELETE prices 端点。"""
    expected = os.environ.get("DDW_LLM_USAGE_ADMIN_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="Admin key not configured")
    if x_admin_key != expected:
        raise HTTPException(status_code=403, detail="Invalid admin key")


def require_service_key(x_service_key: str | None = Header(default=None)) -> None:
    """校验 X-Service-Key header，用于 POST records 端点。"""
    expected = os.environ.get("DDW_LLM_USAGE_SERVICE_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="Service key not configured")
    if x_service_key != expected:
        raise HTTPException(status_code=403, detail="Invalid service key")


# ---------------------------------------------------------------------------
# 响应模型
# ---------------------------------------------------------------------------


class RecordResponse(BaseModel):
    created: bool = Field(..., description="True=新增，False=幂等命中（已存在忽略）")
    record: UsageRecord


class SummaryResponse(BaseModel):
    days: int
    calls: int
    input_tokens: int
    output_tokens: int
    cache_hit_tokens: int
    total_tokens: int
    total_cents: int


class PriceListResponse(BaseModel):
    prices: list[ModelPrice]


class HealthResponse(BaseModel):
    plugin: str
    version: str
    db_path: str
    record_count: int
    model_count: int


# ---------------------------------------------------------------------------
# 路由注册
# ---------------------------------------------------------------------------


def register_routes(router: APIRouter, plugin: Any) -> None:
    """把所有端点挂到 ``router``（父类创建好的、带 prefix 的 APIRouter）。"""
    storage: UsageStorage = plugin.storage

    # ------------------------------------------------------------------ health
    @router.get("/health", response_model=HealthResponse, tags=[plugin.name])
    def health() -> HealthResponse:
        with storage._conn() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM usage_records").fetchone()["n"]
        prices = storage.list_prices()
        return HealthResponse(
            plugin=plugin.name,
            version=plugin.version,
            db_path=str(storage.db_path),
            record_count=int(count),
            model_count=len(prices),
        )

    # ------------------------------------------------------------------ records
    @router.post(
        "/records",
        response_model=RecordResponse,
        status_code=201,
        tags=[plugin.name],
        dependencies=[Depends(require_service_key)],
    )
    def post_record(body: UsageRecordIn) -> RecordResponse:
        rec, created = storage.record_usage(
            id=body.id,
            ts=body.ts,
            plugin=body.plugin,
            user=body.user,
            model=body.model,
            provider=body.provider,
            input_tokens=body.input_tokens,
            output_tokens=body.output_tokens,
            cache_hit_tokens=body.cache_hit_tokens,
            session_id=body.session_id,
        )
        return RecordResponse(created=created, record=rec)

    # ------------------------------------------------------------------ stats
    @router.get("/stats/summary", response_model=SummaryResponse, tags=[plugin.name])
    def stats_summary(days: int = Query(7, ge=1, le=365)) -> SummaryResponse:
        return SummaryResponse(**storage.summary(days))

    @router.get("/stats/by-model", tags=[plugin.name])
    def stats_by_model(days: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
        return {"days": days, "items": storage.by_model(days)}

    @router.get("/stats/by-plugin", tags=[plugin.name])
    def stats_by_plugin(days: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
        return {"days": days, "items": storage.by_plugin(days)}

    @router.get("/stats/by-user", tags=[plugin.name])
    def stats_by_user(days: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
        return {"days": days, "items": storage.by_user(days)}

    @router.get("/stats/daily", tags=[plugin.name])
    def stats_daily(days: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
        return {"days": days, "items": storage.daily(days)}

    # ------------------------------------------------------------------ prices
    @router.get("/prices", response_model=PriceListResponse, tags=[plugin.name])
    def list_prices() -> PriceListResponse:
        return PriceListResponse(prices=list(storage.list_prices().values()))

    @router.put(
        "/prices/{model}",
        response_model=ModelPrice,
        tags=[plugin.name],
        dependencies=[Depends(require_admin_key)],
    )
    def update_price(
        model: str = Path(..., min_length=1),
        body: ModelPriceUpdate = ...,
    ) -> ModelPrice:
        price = ModelPrice(
            model=model,
            input_price=body.input_price,
            output_price=body.output_price,
            cache_hit_price=body.cache_hit_price,
            provider=body.provider,
        )
        storage.upsert_price(price)
        logger.info("price updated for model: %s", model)
        return price

    @router.delete("/prices/{model}", tags=[plugin.name], dependencies=[Depends(require_admin_key)])  # noqa: E501
    def reset_price(model: str = Path(..., min_length=1)) -> dict[str, Any]:
        n = storage.delete_price(model)
        if n == 0:
            return {
                "model": model,
                "deleted": 0,
                "note": "no override; still using default",
            }
        return {"model": model, "deleted": n}


__all__ = ["register_routes"]
