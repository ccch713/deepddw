"""Minimal SDK stub for standalone testing."""


class PluginBase:
    """Stub PluginBase that mirrors the real sdk.plugin_base.PluginBase interface."""

    name: str = ""
    version: str = ""
    router_prefix: str = ""

    def __init__(self, app=None, config=None, manifest=None):
        self.app = app
        self.config = config
        self.manifest = manifest

    def setup(self) -> None:
        raise NotImplementedError
