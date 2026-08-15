"""DDW 问渠学科包插件（PluginBase）。"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from plugins.ddw_wenqu_tutor import PLUGIN_NAME, VERSION
from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """问渠学科包（物理化学）插件。"""

    name = PLUGIN_NAME
    version = VERSION
    router_prefix = (
        "/api/v1/plugins/ddw_wenqu_tutor"
    )

    def setup(self) -> None:
        from plugins.ddw_wenqu_tutor.router import (
            build_router,
        )

        self._router: APIRouter = build_router()
        self.app.include_router(self._router)

        # Create wenqu tables in the core database
        try:
            from core.database.session import get_engine
            from plugins.ddw_wenqu_tutor.models import WenquBase
            import asyncio

            engine = get_engine()

            async def _create_tables():
                try:
                    async with engine.begin() as conn:
                        await conn.run_sync(WenquBase.metadata.create_all)
                except Exception as exc:  # noqa: BLE001
                    if "already exists" in str(exc):
                        logger.warning("wenqu tables already exist, skip create_all (concurrent/async init)")
                    else:
                        raise

            # If there's a running event loop, schedule it; otherwise run inline
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_create_tables())
            except RuntimeError:
                asyncio.run(_create_tables())

            logger.info(
                "%s %s initialized (tables ensured)",
                PLUGIN_NAME,
                VERSION,
            )
        except Exception as e:
            logger.error(
                "%s %s init error: %s",
                PLUGIN_NAME,
                VERSION,
                e,
            )


# Backward compatibility alias
WenquTutorPlugin = Plugin

__all__ = ["Plugin", "WenquTutorPlugin"]
