"""B9 指标口径字典 - API 路由"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from plugins.ddw_metric_dict.models import (
    MetricAdjudicationRequest,
    MetricAdjudicationResult,
    MetricDefinition,
    MetricRouteRequest,
    MetricRouteResponse,
)
from plugins.ddw_metric_dict.service import (
    CaliberNotFoundError,
    MetricNotFoundError,
    adjudicate,
    create_metric,
    get_metric,
    list_metrics,
    route_metric,
)


def build_router(plugin) -> APIRouter:
    r = APIRouter(prefix=plugin.router_prefix, tags=[plugin.name])

    @r.post("/metrics", response_model=MetricDefinition, status_code=201)
    async def create(metric: MetricDefinition) -> MetricDefinition:
        return create_metric(metric)

    @r.get("/metrics", response_model=list[MetricDefinition])
    async def list_all() -> list[MetricDefinition]:
        return list_metrics()

    @r.get("/metrics/{metric_id}", response_model=MetricDefinition)
    async def detail(metric_id: str) -> MetricDefinition:
        try:
            return get_metric(metric_id)
        except MetricNotFoundError:
            raise HTTPException(status_code=404, detail=f"指标 {metric_id} 不存在")

    @r.post("/metrics/route", response_model=MetricRouteResponse)
    async def route(req: MetricRouteRequest) -> MetricRouteResponse:
        try:
            return route_metric(req)
        except MetricNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except CaliberNotFoundError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @r.post("/metrics/adjudicate", response_model=MetricAdjudicationResult)
    async def adjudicate_endpoint(req: MetricAdjudicationRequest) -> MetricAdjudicationResult:
        try:
            return adjudicate(req)
        except MetricNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))

    return r
