"""Internationalisation helpers (PRD §18.11).

The platform supports per-plugin ``locales/<lang>.json`` files
that the :func:`t` helper consults. The current language is stored
on a contextvar so concurrent requests don't clash.
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_current_lang: ContextVar[str] = ContextVar("ddw_lang", default="zh-CN")

# Default bundled strings (zh-CN ↔ en) — bundled with the platform itself.
_BUILTIN: Dict[str, Dict[str, str]] = {
    "zh-CN": {
        "common.ok": "确定",
        "common.cancel": "取消",
        "auth.sms_sent": "验证码已发送",
        "auth.invalid_code": "验证码无效",
    },
    "en": {
        "common.ok": "OK",
        "common.cancel": "Cancel",
        "auth.sms_sent": "Verification code sent",
        "auth.invalid_code": "Invalid code",
    },
}


def set_language(lang: str) -> None:
    _current_lang.set(lang)


def get_language() -> str:
    return _current_lang.get()


def t(key: str, default: Optional[str] = None, *, lang: Optional[str] = None) -> str:
    """Look up ``key`` in the active language; fall back to en, then default."""

    lang = lang or get_language()
    table = _BUILTIN.get(lang) or _BUILTIN.get("en") or {}
    en_table = _BUILTIN.get("en") or {}
    return table.get(key) or en_table.get(key) or default or key


def load_plugin_locales(plugin_dir: Path) -> Dict[str, Dict[str, str]]:
    """Load any ``locales/<lang>.json`` files from ``plugin_dir``."""

    out: Dict[str, Dict[str, str]] = {}
    locales_dir = plugin_dir / "locales"
    if not locales_dir.exists():
        return out
    for f in locales_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("bad locale file %s: %s", f, exc)
            continue
        out[f.stem] = data
    return out
