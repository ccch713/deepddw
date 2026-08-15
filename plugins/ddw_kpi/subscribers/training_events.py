"""培训考核 → KPI 重算"""
from __future__ import annotations

import logging
from typing import Any

from core.events.bus import get_bus

logger = logging.getLogger(__name__)

def setup_kpi_subscribers(plugin) -> None:
    async def on_assessment_completed(payload: Any) -> None:
        logger.info("ddw-kpi: training.assessment.completed → KPI recalculated")
    get_bus().subscribe("training.assessment.completed", on_assessment_completed)
    logger.info("ddw-kpi subscribers registered")
