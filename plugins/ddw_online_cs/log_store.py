"""对话日志落盘 — JSONL 追加写、按天切分、30 天轮转."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

LOG_DIR = Path(__file__).resolve().parent / "logs"
RETENTION_DAYS = 30


def log_today_path() -> Path:
    """返回今天的日志文件路径: logs/YYYY-MM-DD.jsonl."""
    today = time.strftime("%Y-%m-%d")
    return LOG_DIR / f"{today}.jsonl"


def append_chat(
    session_id: str,
    mode: str,
    user_msg: str,
    ai_reply: str,
    source: str,
    duration_ms: int,
    has_attachment: bool = False,
) -> None:
    """追加一条对话记录到当天 JSONL 文件."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": _now_iso(),
            "session_id": session_id,
            "mode": mode,
            "user_msg": user_msg,
            "ai_reply": ai_reply,
            "source": source,
            "duration_ms": duration_ms,
            "has_attachment": has_attachment,
        }
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with open(log_today_path(), "a", encoding="utf-8") as f:
            f.write(line)
        _maybe_cleanup()
    except Exception as exc:
        logger.warning("log_store append failed: %s", exc)


def read_day(date_str: str) -> List[Dict]:
    """读回某天全部日志行（用于 insights），文件不存在返回 []."""
    try:
        p = LOG_DIR / f"{date_str}.jsonl"
        if not p.exists():
            return []
        records: List[Dict] = []
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return records
    except Exception as exc:
        logger.warning("log_store read_day failed: %s", exc)
        return []


def cleanup() -> None:
    """删除超过 RETENTION_DAYS 的旧日志文件."""
    try:
        if not LOG_DIR.exists():
            return
        cutoff = time.time() - RETENTION_DAYS * 86400
        for p in LOG_DIR.glob("*.jsonl"):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink()
            except Exception as exc:
                logger.warning("log_store cleanup unlink failed: %s", exc)
    except Exception as exc:
        logger.warning("log_store cleanup failed: %s", exc)


def _now_iso() -> str:
    """返回 ISO8601+08:00 时间戳."""
    tz = time.timezone if time.daylight == 0 else time.altzone
    offset = -tz
    sign = "+" if offset >= 0 else "-"
    abs_off = abs(offset)
    hh, mm = divmod(abs_off, 3600)
    return time.strftime(f"%Y-%m-%dT%H:%M:%S{sign}{hh:02d}:{mm:02d}")


def _maybe_cleanup() -> None:
    """每次 append 前以 1% 概率触发清理（抽样调用）."""
    import random
    if random.random() < 0.01:
        cleanup()
