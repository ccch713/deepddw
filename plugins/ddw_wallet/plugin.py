"""DDW Wallet 插件（PluginBase）。"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from plugins.ddw_wallet import PLUGIN_NAME, VERSION
from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """预付费钱包插件。"""

    name = PLUGIN_NAME
    version = VERSION
    router_prefix = "/api/v1/plugins/ddw_wallet"

    def setup(self) -> None:
        from plugins.ddw_wallet.router import (
            build_router,
        )

        self._router: APIRouter = build_router()
        self.app.include_router(self._router)

        # Create wallet tables in the core database
        try:
            import asyncio

            from core.database.session import get_engine
            from plugins.ddw_wallet.models import WalletBase

            engine = get_engine()

            async def _create_tables() -> None:
                async with engine.begin() as conn:
                    await conn.run_sync(
                        WalletBase.metadata.create_all
                    )

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_create_tables())
            except RuntimeError:
                asyncio.run(_create_tables())

            try:
                from plugins.ddw_wallet.router import start_callback_worker
                loop.create_task(start_callback_worker())
            except Exception as exc:  # noqa: BLE001
                logger.warning("Callback worker start failed: %s", exc)
            logger.info(
                "%s %s initialized (tables ensured)",
                PLUGIN_NAME,
                VERSION,
            )
        except Exception as e:  # noqa: BLE001
            logger.error(
                "%s %s init error: %s",
                PLUGIN_NAME,
                VERSION,
                e,
            )


__all__ = ["Plugin"]
