"""DDW KPI Dashboard - FastAPI router."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .aggregator import doctors, overview, treatments, trend
from .aggregator import patients as agg_patients

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/plugins/ddw_kpi_dashboard", tags=["ddw_kpi_dashboard"]
)

# 由 plugin.py 注入
_db_path = None


def set_db_path(p) -> None:
    global _db_path
    _db_path = p


def _db() -> Path:
    if _db_path is None:
        raise HTTPException(status_code=503, detail="plugin not initialized")
    return Path(_db_path)


class HealthResponse(BaseModel):
    plugin: str = "ddw_kpi_dashboard"
    version: str = "0.1.0"
    status: str = "ok"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


def _default_period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


@router.get("/overview")
async def get_overview(period: Optional[str] = None) -> dict:
    p = period or _default_period()
    return overview(_db(), p)


@router.get("/doctors")
async def get_doctors(period: Optional[str] = None) -> dict:
    p = period or _default_period()
    items = doctors(_db(), p)
    return {"period": p, "doctors": items}


@router.get("/treatments")
async def get_treatments(period: Optional[str] = None) -> dict:
    p = period or _default_period()
    items = treatments(_db(), p)
    return {"period": p, "treatments": items}


@router.get("/patients")
async def get_patients(period: Optional[str] = None) -> dict:
    p = period or _default_period()
    by_source = agg_patients(_db(), p)
    return {"period": p, "by_source": by_source}


@router.get("/trend")
async def get_trend(months: int = 6) -> dict:
    if months < 1 or months > 36:
        months = 6
    return {"months": months, "trend": trend(_db(), months)}
