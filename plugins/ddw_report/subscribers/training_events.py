"""培训事件订阅"""
from __future__ import annotations

import logging
from typing import Any

from core.events.bus import get_bus

logger = logging.getLogger(__name__)

def setup_report_subscribers(plugin) -> None:
    async def on_session_completed(payload: Any) -> None:
        logger.info("ddw-report: training.session.completed received")
    async def on_assessment_completed(payload: Any) -> None:
        logger.info("ddw-report: training.assessment.completed received")
    get_bus().subscribe("training.session.completed", on_session_completed)
    get_bus().subscribe("training.assessment.completed", on_assessment_completed)
    logger.info("ddw-report subscribers registered")
