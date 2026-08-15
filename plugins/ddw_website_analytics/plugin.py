"""DDW Website Analytics - Plugin class (v0.2.0).

v0.2.0 增量：
    * setup() / initialize() 时挂载 AnticrawlerMiddleware 到 app
    * 暴露 generate_daily_report_for_cron() 给 cron 进程调用
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from sdk.plugin_base import PluginBase

from .log_parser import (
    CaddyLogParser,
    ParsedAggregate,
    aggregate,
)
from .router import _set_aggregator, router
from .store import AnalyticsStore

logger = logging.getLogger(__name__)


def _build_aggregator(
    parser: CaddyLogParser,
    store: AnalyticsStore,
    ttl_sec: int,
):
    state: Dict[str, Any] = {"last_run": 0.0, "cached": None, "lock": threading.Lock()}

    def _compute(days: int) -> ParsedAggregate:
        with state["lock"]:
            now = time.time()
            cached: Optional[ParsedAggregate] = state["cached"]
            if cached is not None and (now - state["last_run"]) < ttl_sec:
                return cached
            try:
                entries = parser.parse_all()
                agg = aggregate(entries, period_days=days)
            except Exception as exc:  # noqa: BLE001
                agg = ParsedAggregate()
            try:
                store.set("daily", agg.daily)
                store.set("pages", agg.pages)
                store.set("pages_by_kind", agg.pages_by_kind)
                store.set("referrers", agg.referrers)
                store.set("referrers_business", agg.referrers_business)
                store.set("crawlers", agg.crawlers)
                store.set("ai_crawler_breakdown", agg.ai_crawler_breakdown)
                store.set("risk_distribution", agg.risk_distribution)
                store.set(
                    f"summary:{days}d",
                    {
                        "total_pv": agg.total_pv,
                        "total_uv": agg.total_uv,
                        "business_pv": agg.business_pv,
                        "business_uv": agg.business_uv,
                        "today_pv": agg.today_pv,
                        "today_uv": agg.today_uv,
                        "today_business_pv": agg.today_business_pv,
                        "api_pv": agg.api_pv,
                        "static_pv": agg.static_pv,
                        "bounce_count": agg.bounce_count,
                        "session_count": agg.session_count,
                        "ai_crawler_requests": agg.ai_crawler_requests,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("cache write skipped: %s", exc)
            state["cached"] = agg
            state["last_run"] = now
            return agg

    return _compute


class Plugin(PluginBase):
    """DDW Website Analytics - Plugin entry class."""

    name = "ddw_website_analytics"
    version = "0.2.0"
    description = "网站访问/访客数据报表（解析 Caddy JSON access log）+ 反爬虫中间件 + 每日报告"

    def __init__(self, manifest=None, **kwargs: Any) -> None:
        app = kwargs.get("app")
        config = kwargs.get("config") or {}
        if manifest is None:
            manifest = kwargs.get("manifest")
        # 插件三铁律①：setup() 在 PluginBase.__init__ 内自动调用，
        # 其依赖的属性必须在 super().__init__() 之前初始化
        self._anticrawler_attached: bool = False
        super().__init__(app=app, config=config, manifest=manifest)
        self.router = router

        self._store: Optional[AnalyticsStore] = None
        self._parser: Optional[CaddyLogParser] = None
        self._aggregator_fn = None
        self._router = router

    def register(self) -> None:
        """Override: register router + initialize log parser/aggregator."""
        logger.info("ddw_website_analytics.register() called, has _anticrawler_attached=%s", hasattr(self, "_anticrawler_attached"))
        try:
            super().register()
            logger.info("ddw_website_analytics super().register() done")
        except Exception as exc:
            logger.exception("super().register() failed: %s", exc)
            raise
        try:
            self.setup()
        except Exception as exc:
            logger.exception("self.setup() failed: %s", exc)
            raise
        logger.info("ddw_website_analytics setup() done, aggregator=%s", self._aggregator_fn is not None)

    # ---- SDK v2 lifecycle ------------------------------------------------

    async def initialize(self) -> None:
        cfg = self.config or {}
        log_paths = cfg.get("log_paths") or [
            "/root/ecs-framework/caddy/logs/*_access.log",
            "/var/log/caddy/*_access.log",
        ]
        cache_db_rel = cfg.get("cache_db") or "plugins/ddw_website_analytics/data/analytics.db"
        cache_db_path = Path(cache_db_rel)
        if not cache_db_path.is_absolute():
            cache_db_path = Path(__file__).resolve().parent / cache_db_rel
        ttl_sec = int(cfg.get("cache_ttl_sec") or 3600)
        anticrawler_enabled = bool(cfg.get("anticrawler_enabled", True))

        self._store = AnalyticsStore(db_path=Path(cache_db_path))
        self._parser = CaddyLogParser(paths=log_paths)
        self._aggregator_fn = _build_aggregator(
            parser=self._parser,
            store=self._store,
            ttl_sec=ttl_sec,
        )
        _set_aggregator(self._aggregator_fn)

        # 挂载反爬虫中间件
        if anticrawler_enabled and self.app is not None:
            already = getattr(self, "_anticrawler_attached", False)
            if not already:
                try:
                    from .anticrawler import AnticrawlerMiddleware
                    self.app.add_middleware(AnticrawlerMiddleware)
                    self._anticrawler_attached = True
                    logger.info("AnticrawlerMiddleware attached to app")
                except Exception as exc:
                    logger.warning("anticrawler middleware attach failed: %s", exc)

        try:
            await super().initialize()
        except Exception:  # noqa: BLE001
            pass

    async def start(self) -> None:
        try:
            await super().start()
        except Exception:  # noqa: BLE001
            pass

    async def stop(self) -> None:
        try:
            await super().stop()
        except Exception:  # noqa: BLE001
            pass

    # ---- SDK v1 lifecycle (legacy) ----------------------------------------

    def setup(self) -> None:
        cfg = self.config or {}
        log_paths = cfg.get("log_paths") or [
            "/root/ecs-framework/caddy/logs/*_access.log",
            "/var/log/caddy/*_access.log",
        ]
        cache_db_rel = cfg.get("cache_db") or "plugins/ddw_website_analytics/data/analytics.db"
        cache_db_path = Path(cache_db_rel)
        if not cache_db_path.is_absolute():
            cache_db_path = Path(__file__).resolve().parent.parent.parent / cache_db_rel
        ttl_sec = int(cfg.get("cache_ttl_sec") or 3600)
        anticrawler_enabled = bool(cfg.get("anticrawler_enabled", True))

        self._store = AnalyticsStore(db_path=Path(cache_db_path))
        self._parser = CaddyLogParser(paths=log_paths)
        self._aggregator_fn = _build_aggregator(
            parser=self._parser,
            store=self._store,
            ttl_sec=ttl_sec,
        )
        _set_aggregator(self._aggregator_fn)
        self._router = router
        if self.app is not None and hasattr(self.app, "include_router"):
            self.app.include_router(router)

        # 挂载反爬虫中间件
        if anticrawler_enabled and self.app is not None and not self._anticrawler_attached:
            try:
                from .anticrawler import AnticrawlerMiddleware
                self.app.add_middleware(AnticrawlerMiddleware)
                self._anticrawler_attached = True
                logger.info("AnticrawlerMiddleware attached to app")
            except Exception as exc:
                logger.warning("anticrawler middleware attach failed: %s", exc)

    # ---- 公开给 cron 调用的工具方法 ----------------------------------------

    def generate_daily_report(self):
        """同步生成报告（cron / manual 调用）。"""
        from .insights_engine import generate_daily_report as _gen
        return _gen(aggregator_fn=self._aggregator_fn)

    def list_snapshots(self, limit: int = 30):
        from .insights_engine import list_snapshots as _list
        return _list(limit=limit)
