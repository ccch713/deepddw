"""DDW Aggregated Pay — Plugin.

⛔ DEPRECATED 2026-08-12 — 已终止
详见 __init__.py 横幅说明。
"""
from sdk.plugin_base import PluginBase

from .router import router, set_store
from .store import AggregatedPayStore


class Plugin(PluginBase):
    name = "ddw_aggregated_pay"
    version = "0.1.0"
    description = "[DEPRECATED 2026-08-12] 聚合支付与对账 — 已终止，请用 ddw_wallet"

    def __init__(self, app=None, config=None, manifest=None, **kwargs):
        super().__init__(app, config)
        self._store = None

    async def initialize(self):
        raise NotImplementedError("ddw_aggregated_pay 已于 2026-08-12 终止。")

    async def start(self):
        raise NotImplementedError("ddw_aggregated_pay 已于 2026-08-12 终止。")

    async def stop(self):
        pass

    def setup(self):
        raise NotImplementedError("ddw_aggregated_pay 已于 2026-08-12 终止。")
