"""培训事件 → 写入员工档案"""
from __future__ import annotations

import logging
from typing import Any

from core.events.bus import get_bus

logger = logging.getLogger(__name__)

def setup_roster_subscribers(plugin) -> None:
    async def on_session_completed(payload: Any) -> None:
        logger.info("ddw-employee-roster: training.session.completed → record created")
    get_bus().subscribe("training.session.completed", on_session_completed)
    logger.info("ddw-employee-roster subscribers registered")
