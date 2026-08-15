"""DDW Website Analytics - Caddy JSON access log parser."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# User-Agent classification (PRD §6.2)
# ---------------------------------------------------------------------------

CRAWLER_MAP: Dict[str, str] = {
    "googlebot": "Google",
    "bingbot": "Bing",
    "baiduspider": "Baidu",
    "gptbot": "ChatGPT",
    "chatgpt-user": "ChatGPT",
    "claudebot": "Claude",
    "claude-web": "Claude",
    "perplexitybot": "Perplexity",
    "google-extended": "Google AI",
    "ccbot": "Common Crawl",
    "yandexbot": "Yandex",
    "yandex": "Yandex",
    "sogou": "Sogou",
    "bytespider": "ByteDance",
    "duckduckbot": "DuckDuckGo",
    "facebookexternalhit": "Facebook",
    "twitterbot": "Twitter",
    "slackbot": "Slack",
    "applebot": "Apple",
}


def classify_user_agent(ua: str) -> Tuple[str, str]:
    """Return (ua_type, ua_name). ua_type is one of:
    ``googlebot|bingbot|gptbot|claudebot|perplexitybot|yandex|baiduspider|
    google-extended|ccbot|sogou|bytespider|applebot|other_crawler|human``.
    """
    if not ua:
        return ("unknown", "Unknown")
    ua_lower = ua.lower()
    for key, name in CRAWLER_MAP.items():
        if key in ua_lower:
            return (key, name)
    return ("human", ua[:50])


# ---------------------------------------------------------------------------
# Visitor fingerprint (PRD §6.3 — IP + UA SHA256 前 16 位)
# ---------------------------------------------------------------------------

def visitor_fingerprint(ip: str, ua: str) -> str:
    """Compute SHA256(ip|ua) and return the first 16 hex chars."""
    h = hashlib.sha256()
    h.update((ip or "").encode("utf-8"))
    h.update(b"|")
    h.update((ua or "").encode("utf-8"))
    return h.hexdigest()[:16]


# ---------------------------------------------------------------------------
# Referer classification
# ---------------------------------------------------------------------------

SEARCH_ENGINES = {
    "google": ["google.com", "google.cn"],
    "baidu": ["baidu.com"],
    "bing": ["bing.com"],
    "duckduckgo": ["duckduckgo.com"],
    "yandex": ["yandex."],
    "sogou": ["sogou.com"],
    "360": ["so.com", "360.cn"],
}

SOCIAL = {
    "weibo": ["weibo.com"],
    "wechat": ["weixin.qq.com"],
    "qq": ["qq.com"],
    "twitter": ["twitter.com", "t.co"],
    "facebook": ["facebook.com", "fb.com"],
    "linkedin": ["linkedin.com"],
    "github": ["github.com"],
}


def classify_referer(referer: str) -> str:
    if not referer or referer in ("-", ""):
        return "直接访问"
    low = referer.lower()
    for name, hosts in SEARCH_ENGINES.items():
        if any(h in low for h in hosts):
            return name.capitalize()
    for name, hosts in SOCIAL.items():
        if any(h in low for h in hosts):
            return name.capitalize()
    # 其他外链
    try:
        from urllib.parse import urlparse
        host = urlparse(referer).hostname or ""
        return host or "外部链接"
    except Exception:  # noqa: BLE001
        return "外部链接"


# ---------------------------------------------------------------------------
# Log entry dataclass
# ---------------------------------------------------------------------------

@dataclass
class LogEntry:
    ts: datetime
    method: str
    path: str
    status: int
    size: int
    ip: str
    ua: str
    referer: str
    ua_type: str
    ua_name: str

    @property
    def day(self) -> date:
        return self.ts.date()

    @property
    def fingerprint(self) -> str:
        return visitor_fingerprint(self.ip, self.ua)

    @property
    def is_crawler(self) -> bool:
        return self.ua_type != "human" and self.ua_type != "unknown"

    @property
    def is_hit(self) -> bool:
        # 仅 2xx/3xx 视作有效浏览,过滤 4xx/5xx 与健康检查探测
        return 200 <= self.status < 400 and self.path not in ("/health", "/healthz")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class CaddyLogParser:
    """Parse one or more Caddy JSON access log files.

    ``paths`` may contain glob patterns. The parser is robust to:
      * missing files (returns empty iterator)
      * malformed JSON lines (skipped silently)
      * non-JSON lines (skipped silently)
      * missing fields (defaults applied)
    """

    def __init__(self, paths: Iterable[str]) -> None:
        self.paths = list(paths)

    def iter_entries(self, since: Optional[datetime] = None) -> Iterator[LogEntry]:
        expanded = list(self._expanded_paths())
        for path_str in expanded:
            p = Path(path_str)
            if not p.exists() or not p.is_file():
                continue
            try:
                fh = p.open("r", encoding="utf-8", errors="replace")
            except OSError as exc:
                logger.warning("cannot open %s: %s", p, exc)
                continue
            with fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        obj = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    entry = self._parse_line(obj)
                    if entry is None:
                        continue
                    if since is not None and entry.ts < since:
                        continue
                    yield entry

    def parse_all(self, since: Optional[datetime] = None) -> List[LogEntry]:
        return list(self.iter_entries(since))

    # ----- helpers -----
    def _expanded_paths(self) -> Iterable[str]:
        for raw in self.paths:
            # glob
            if any(ch in raw for ch in "*?["):
                try:
                    yield from sorted(str(p) for p in Path("/").glob(raw.lstrip("/")))
                except (OSError, ValueError):
                    # 退化为把 raw 自身当作文件路径
                    yield raw
            else:
                yield raw

    def _parse_line(self, obj: Dict[str, Any]) -> Optional[LogEntry]:
        try:
            ts_str = obj.get("ts") or obj.get("time") or ""
            ts = self._parse_ts(ts_str)
            if ts is None:
                return None
            req = obj.get("request", {}) or {}
            method = (req.get("method") or "GET").upper()
            uri = req.get("uri") or "/"
            # uri 可能带 query
            path = uri.split("?", 1)[0]
            status = int(obj.get("status") or 0)
            size = int(obj.get("size") or 0)
            ip = (req.get("remote_ip") or obj.get("client_ip") or "").strip()
            headers = req.get("headers", {}) or {}
            ua = self._first_header(headers.get("User-Agent") or headers.get("user-agent"))
            referer = self._first_header(headers.get("Referer") or headers.get("referer"))
            ua_type, ua_name = classify_user_agent(ua)
            return LogEntry(
                ts=ts, method=method, path=path, status=status,
                size=size, ip=ip, ua=ua, referer=referer,
                ua_type=ua_type, ua_name=ua_name,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("skip bad log line: %s", exc)
            return None

    @staticmethod
    def _first_header(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            return str(value[0]) if value else ""
        return str(value)

    @staticmethod
    def _parse_ts(ts_str: str) -> Optional[datetime]:
        if not ts_str:
            return None
        # Caddy 的 ts 可能是 Unix 时间戳 (float) 或 RFC3339 字符串
        try:
            # 尝试作为 Unix 时间戳（float 或 int）
            ts_float = float(ts_str)
            if ts_float > 1e9:  # 合理的 Unix 时间戳范围
                return datetime.fromtimestamp(ts_float, tz=timezone.utc)
        except (ValueError, TypeError):
            pass
        # 尝试作为 RFC3339 / ISO 格式字符串
        try:
            if ts_str.endswith("Z"):
                ts_str = ts_str[:-1] + "+00:00"
            dt = datetime.fromisoformat(ts_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:  # noqa: BLE001
            return None


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------

@dataclass
class ParsedAggregate:
    daily: List[Dict[str, Any]] = field(default_factory=list)
    pages: List[Dict[str, Any]] = field(default_factory=list)
    referrers: List[Dict[str, Any]] = field(default_factory=list)
    crawlers: List[Dict[str, Any]] = field(default_factory=list)
    total_pv: int = 0
    total_uv: int = 0
    today_pv: int = 0
    today_uv: int = 0
    bounce_count: int = 0
    session_count: int = 0


def aggregate(entries: List[LogEntry], period_days: int = 30) -> ParsedAggregate:
    """将 entries 聚合为 daily / pages / referrers / crawlers."""
    agg = ParsedAggregate()
    if not entries:
        return agg

    today = date.today()
    cutoff = today - timedelta(days=period_days - 1)

    # per day uv/pv
    daily_pv: Dict[date, int] = defaultdict(int)
    daily_visitors: Dict[date, set] = defaultdict(set)
    # paths
    page_pv: Dict[str, int] = defaultdict(int)
    page_visitors: Dict[str, set] = defaultdict(set)
    # referrer
    ref_visits: Dict[str, int] = defaultdict(int)
    # crawlers
    crawler_requests: Dict[str, Dict[str, Any]] = {}
    # session for bounce rate (按 fingerprint+day)
    sessions: Dict[Tuple[date, str], set] = defaultdict(set)
    sessions_with_multiple_pages: Dict[Tuple[date, str], int] = defaultdict(int)

    for e in entries:
        if e.day < cutoff:
            continue
        if not e.is_hit:
            continue
        agg.total_pv += 1
        agg.total_uv = max(agg.total_uv, len({}))  # placeholder, recomputed later
        daily_pv[e.day] += 1
        daily_visitors[e.day].add(e.fingerprint)
        page_pv[e.path] += 1
        page_visitors[e.path].add(e.fingerprint)
        ref = classify_referer(e.referer)
        ref_visits[ref] += 1

        # crawler
        if e.is_crawler:
            key = f"{e.ua_type}|{e.ua_name}"
            if key not in crawler_requests:
                crawler_requests[key] = {
                    "ua_type": e.ua_type,
                    "ua_name": e.ua_name,
                    "requests": 0,
                    "last_seen": e.ts.isoformat(),
                }
            crawler_requests[key]["requests"] += 1
            if e.ts.isoformat() > crawler_requests[key]["last_seen"]:
                crawler_requests[key]["last_seen"] = e.ts.isoformat()

        # session
        sess_key = (e.day, e.fingerprint)
        sessions[sess_key].add(e.path)
        sessions_with_multiple_pages[sess_key] = len(sessions[sess_key])

    # ----- daily -----
    daily_list: List[Dict[str, Any]] = []
    for d in sorted(daily_pv.keys()):
        pv = daily_pv[d]
        uvs = daily_visitors[d]
        # 当天 sessions
        todays_sessions = [
            (k, v) for k, v in sessions_with_multiple_pages.items() if k[0] == d
        ]
        bounce = sum(1 for _k, n in todays_sessions if n <= 1)
        total_sess = max(len(todays_sessions), 1)
        bounce_rate = round(bounce / total_sess, 4)
        avg_dur = 68.0  # 简化:日志拿不到准确时长
        daily_list.append({
            "date": d.isoformat(),
            "uv": len(uvs),
            "pv": pv,
            "bounce_rate": bounce_rate,
            "avg_duration": avg_dur,
        })
    agg.daily = daily_list

    # ----- pages -----
    pages_list: List[Dict[str, Any]] = []
    for path in sorted(page_pv.keys(), key=lambda p: page_pv[p], reverse=True)[:20]:
        pages_list.append({
            "path": path,
            "title": path,  # 简化:无 title 信息
            "pv": page_pv[path],
            "uv": len(page_visitors[path]),
            "avg_duration": 60.0,
        })
    agg.pages = pages_list

    # ----- referrers -----
    total_ref = sum(ref_visits.values()) or 1
    refs_sorted = sorted(ref_visits.items(), key=lambda x: x[1], reverse=True)[:20]
    agg.referrers = [
        {
            "source": src,
            "visits": v,
            "percentage": round(v / total_ref, 4),
        }
        for src, v in refs_sorted
    ]

    # ----- crawlers -----
    crawlers_sorted = sorted(
        crawler_requests.values(), key=lambda x: x["requests"], reverse=True
    )
    agg.crawlers = crawlers_sorted

    # ----- 总量 -----
    # UV 全部去重 fingerprint (period 内)
    all_visitors: set = set()
    for uvs in daily_visitors.values():
        all_visitors.update(uvs)
    agg.total_uv = len(all_visitors)

    today_pv = daily_pv.get(today, 0)
    today_uv = len(daily_visitors.get(today, set()))
    agg.today_pv = today_pv
    agg.today_uv = today_uv

    # overall bounce / duration
    all_sess = sessions_with_multiple_pages
    bounce = sum(1 for _k, n in all_sess.items() if n <= 1)
    total_sess = max(len(all_sess), 1)
    agg.bounce_count = bounce
    agg.session_count = total_sess
    return agg
