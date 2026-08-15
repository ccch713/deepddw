from sdk.plugin_base import PluginBase
from . import PLUGIN_NAME, VERSION
from .router import build_router


class Plugin(PluginBase):
    name = PLUGIN_NAME
    version = VERSION
    router_prefix = f"/api/v1/plugins/{PLUGIN_NAME}"

    def setup(self) -> None:
        # 只建 router，挂载交给 SDK 的 register() 统一处理（避免双挂）
        self._router = build_router()
