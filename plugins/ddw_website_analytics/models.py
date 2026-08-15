"""DDW Website Analytics - Pydantic 模型."""
from __future__ import annotations

from datetime import date
from typing import List

from pydantic import BaseModel


class DailyStats(BaseModel):
    date: date
    uv: int
    pv: int
    bounce_rate: float
    avg_duration: float


class PageStats(BaseModel):
    path: str
    title: str
    pv: int
    uv: int
    avg_duration: float


class ReferrerStats(BaseModel):
    source: str
    visits: int
    percentage: float


class CrawlerStats(BaseModel):
    ua_type: str
    ua_name: str
    requests: int
    last_seen: str


class AnalyticsSummary(BaseModel):
    total_pv: int
    total_uv: int
    today_pv: int
    today_uv: int
    bounce_rate: float
    avg_duration: float
    top_pages: List[PageStats]
    top_referrers: List[ReferrerStats]
    daily_trend: List[DailyStats]
    crawler_stats: List[CrawlerStats]
    period: str
