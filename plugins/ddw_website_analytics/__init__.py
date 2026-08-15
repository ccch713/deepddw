"""DDW Website Analytics Plugin.

提供网站访问/访客数据报表（解析 Caddy JSON access log）。
"""
from __future__ import annotations

__all__ = ["Plugin", "PLUGIN_NAME", "VERSION"]

PLUGIN_NAME = "ddw_website_analytics"
VERSION = "0.1.0"


def register(app):  # pragma: no cover - convenience entry for SDK v1 loaders
    """SDK v1 register hook."""
    from .plugin import Plugin

    plugin = Plugin(app=app, config={}, manifest={})
    plugin.setup()
    if hasattr(app, "include_router"):
        from .router import router

        app.include_router(router)
    return plugin


# Eager re-exports for convenience
from .plugin import Plugin  # noqa: E402,F401  (after PLUGIN_NAME so name wins)
from .log_parser import (  # noqa: E402,F401
    CRAWLER_MAP,
    CaddyLogParser,
    LogEntry,
    ParsedAggregate,
    aggregate,
    classify_user_agent,
    classify_referer,
    visitor_fingerprint,
)
from .models import (  # noqa: E402,F401
    AnalyticsSummary,
    CrawlerStats,
    DailyStats,
    PageStats,
    ReferrerStats,
)
from .router import router  # noqa: E402,F401
from .store import AnalyticsStore  # noqa: E402,F401
