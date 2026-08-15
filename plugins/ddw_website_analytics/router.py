"""DDW Website Analytics - FastAPI router."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .log_parser import (
    ParsedAggregate,
    aggregate,
    CaddyLogParser,
)
from .models import (
    AnalyticsSummary,
    CrawlerStats,
    DailyStats,
    PageStats,
    ReferrerStats,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/plugins/ddw_website_analytics",
    tags=["ddw_website_analytics"],
)

# Lazy aggregator reference (injected by plugin.initialize()).
_aggregator: Optional[Callable[..., ParsedAggregate]] = None


_AGGREGATOR_KEY = "ddw_website_analytics._aggregator_ref"


def _set_aggregator(fn: Callable[..., ParsedAggregate]) -> None:
    """Store the aggregator callable in a namespace-safe location."""
    import sys
    sys.modules[_AGGREGATOR_KEY] = fn  # type: ignore[assignment]


def _default_aggregator(period_days: int = 30) -> ParsedAggregate:
    """Build a no-data aggregator for cold start."""
    return ParsedAggregate()


def _ensure_aggregator() -> Callable[..., ParsedAggregate]:
    import sys, logging
    _dbg = logging.getLogger("ddw_website_analytics.router")
    ref = sys.modules.get(_AGGREGATOR_KEY)
    if ref is not None:
        return ref
    return _default_aggregator


# ---- Auth dependency -----------------------------------------------------
try:
    from core.auth.dependencies import require_user  # type: ignore
except Exception:  # noqa: BLE001
    def require_user():  # type: ignore
        return {"username": "anonymous"}


# ---- Period helpers ------------------------------------------------------

def _parse_period(period: str) -> int:
    """Map ``7d`` / ``30d`` to an int day count. Default to 7."""
    if not period:
        return 7
    s = period.strip().lower()
    if s.endswith("d"):
        try:
            n = int(s[:-1])
            return n if n > 0 else 7
        except ValueError:
            return 7
    if s.endswith("h"):
        try:
            return max(1, int(int(s[:-1]) / 24))
        except ValueError:
            return 1
    return 7


# ---- Endpoints -----------------------------------------------------------

@router.get("/health")
async def health(_user: dict = Depends(require_user)) -> dict:
    return {
        "plugin": "ddw_website_analytics",
        "version": "0.1.0",
        "status": "ok",
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/summary", response_model=AnalyticsSummary)
async def summary(
    period: str = Query("7d", description="7d / 30d"),
    _user: dict = Depends(require_user),
) -> AnalyticsSummary:
    try:
        days = _parse_period(period)
        agg = _ensure_aggregator()(days)
        bounce_rate = (
            round(agg.bounce_count / agg.session_count, 4)
            if agg.session_count else 0.0
        )
        return AnalyticsSummary(
            total_pv=agg.total_pv,
            total_uv=agg.total_uv,
            today_pv=agg.today_pv,
            today_uv=agg.today_uv,
            bounce_rate=bounce_rate,
            avg_duration=68.0,
            top_pages=[PageStats(**p) for p in agg.pages[:10]],
            top_referrers=[ReferrerStats(**r) for r in agg.referrers[:10]],
            daily_trend=[DailyStats(**d) for d in agg.daily],
            crawler_stats=[CrawlerStats(**c) for c in agg.crawlers],
            period=period,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("summary failed: %s", exc)
        return AnalyticsSummary(
            total_pv=0, total_uv=0, today_pv=0, today_uv=0,
            bounce_rate=0.0, avg_duration=0.0,
            top_pages=[], top_referrers=[],
            daily_trend=[], crawler_stats=[], period=period,
        )


@router.get("/daily", response_model=List[DailyStats])
async def daily(
    period: str = Query("30d", description="7d / 30d"),
    _user: dict = Depends(require_user),
) -> List[DailyStats]:
    try:
        days = _parse_period(period)
        agg = _ensure_aggregator()(days)
        return [DailyStats(**d) for d in agg.daily]
    except Exception as exc:  # noqa: BLE001
        logger.exception("daily failed: %s", exc)
        return []


@router.get("/pages", response_model=List[PageStats])
async def pages(
    limit: int = Query(20, ge=1, le=100),
    _user: dict = Depends(require_user),
) -> List[PageStats]:
    try:
        agg = _ensure_aggregator()(30)
        return [PageStats(**p) for p in agg.pages[:limit]]
    except Exception as exc:  # noqa: BLE001
        logger.exception("pages failed: %s", exc)
        return []


@router.get("/referrers", response_model=List[ReferrerStats])
async def referrers(
    limit: int = Query(20, ge=1, le=100),
    _user: dict = Depends(require_user),
) -> List[ReferrerStats]:
    try:
        agg = _ensure_aggregator()(30)
        return [ReferrerStats(**r) for r in agg.referrers[:limit]]
    except Exception as exc:  # noqa: BLE001
        logger.exception("referrers failed: %s", exc)
        return []


@router.get("/crawlers", response_model=List[CrawlerStats])
async def crawlers(
    period: str = Query("30d", description="7d / 30d"),
    _user: dict = Depends(require_user),
) -> List[CrawlerStats]:
    try:
        days = _parse_period(period)
        agg = _ensure_aggregator()(days)
        return [CrawlerStats(**c) for c in agg.crawlers]
    except Exception as exc:  # noqa: BLE001
        logger.exception("crawlers failed: %s", exc)
        return []


@router.post("/refresh", status_code=status.HTTP_200_OK)
async def refresh(_user: dict = Depends(require_user)) -> dict:
    """Trigger re-aggregation. Implementation lives in plugin (rebuild cache)."""
    try:
        # Force re-parse next call
        agg = _ensure_aggregator()(30)
        return {
            "ok": True,
            "ts": datetime.now(timezone.utc).isoformat(),
            "total_pv": agg.total_pv,
            "total_uv": agg.total_uv,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("refresh failed: %s", exc)
        return {
            "ok": False,
            "error": str(exc),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
