"""Chinese font registration for reportlab PDF generation.

Tries multiple system font paths on macOS; falls back to Helvetica
if no Chinese font is available.
"""

from __future__ import annotations

import logging
import os

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

_FONT_REGISTERED = False
_FONT_NAME = "Helvetica"


def register_fonts() -> str:
    """Register a Chinese-capable font with reportlab.

    Returns the registered font name (or 'Helvetica' as fallback).
    """
    global _FONT_REGISTERED, _FONT_NAME  # noqa: PLW0603

    if _FONT_REGISTERED:
        return _FONT_NAME

    font_paths = [
        "/System/Library/Fonts/Supplemental/NotoSansSC-Regular.otf",
        "/Library/Fonts/NotoSansSC-Regular.otf",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansSC-Regular.otf",
    ]

    for path in font_paths:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("ChineseFont", path))
                _FONT_NAME = "ChineseFont"
                _FONT_REGISTERED = True
                logger.info("Registered Chinese font: %s", path)
                return _FONT_NAME
            except Exception as exc:
                logger.warning("Failed to register font %s: %s", path, exc)

    logger.warning("No Chinese font found — falling back to Helvetica")
    _FONT_NAME = "Helvetica"
    _FONT_REGISTERED = True
    return _FONT_NAME


def get_font_name() -> str:
    """Get the current font name, registering if needed."""
    if not _FONT_REGISTERED:
        register_fonts()
    return _FONT_NAME
