"""PluginBase - Abstract base class for all DDW plugins (SDK v2 merged).

v2 merge (2026-08-01):
  * New lifecycle contract: ``PluginBase(config)`` ABC with
    initialize/start/stop/health + 5-state FSM (CREATED/INITIALIZED/
    RUNNING/DEGRADED/STOPPED).
  * Backward-compatible constructor: also accepts the legacy
    ``PluginBase(app, config, manifest)`` call shape (SDK v1).
  * SDK helpers: ``ExecutionTrace``, ``InterventionHooks``,
    ``traced_operation``.
  * Legacy names preserved: ``DDWPlugin`` alias, ``PluginContext``,
    ``LegacyPluginBase``.
"""

from __future__ import annotations

import time
import uuid
from abc import ABC
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from sdk.plugin_state import PluginState


class PluginBase(ABC):
    """Base class for all DDW plugins.

    Subclasses must:
        * Set class attributes ``name`` and ``version``.
        * Implement :meth:`initialize`, :meth:`start`, :meth:`stop`.
        * Optionally override :meth:`health` to expose richer health info.

    Constructor is compatible with both SDK v2 (``PluginBase(config)``)
    and SDK v1 (``PluginBase(app, config, manifest)``) call shapes.
    """

    # Class-level metadata (overridden in subclasses)
    name: str = "unnamed-plugin"
    version: str = "0.0.0"
    description: str = ""

    def __init__(
        self,
        app: Any = None,
        config: Optional[dict[str, Any]] = None,
        manifest: Optional[dict[str, Any]] = None,
    ) -> None:
        # SDK v2 shape: PluginBase(config) -- first arg is config dict.
        if isinstance(app, dict) and config is None:
            config = app
            app = None
        self.app: Any = app
        self.config: dict[str, Any] = dict(config or {})
        self.manifest: dict[str, Any] = dict(manifest or {})
        self.state: PluginState = PluginState.CREATED
        self.plugin_id: str = str(uuid.uuid4())
        self._created_at: datetime = datetime.now(timezone.utc)

    # ---- Lifecycle hooks (subclasses override) ----

    async def initialize(self) -> None:
        """Prepare resources (DB connections, clients)."""

    async def start(self) -> None:
        """Begin serving."""

    async def stop(self) -> None:
        """Graceful shutdown."""

    async def health(self) -> dict[str, Any]:
        """Return health metadata. Default returns the FSM state."""
        return {
            "plugin": self.name,
            "version": self.version,
            "state": self.state.value,
        }

    # ---- State machine helpers ----

    def _transition(self, target: PluginState) -> None:
        """Perform an FSM transition or raise ``ValueError``."""
        if not PluginState.can_transition(self.state, target):
            raise ValueError(
                f"Invalid state transition for {self.name}: "
                f"{self.state.value} -> {target.value}"
            )
        self.state = target

    async def bootstrap(self) -> None:
        """Convenience: CREATED -> INITIALIZED -> RUNNING."""
        self._transition(PluginState.INITIALIZED)
        await self.initialize()
        self._transition(PluginState.RUNNING)
        await self.start()

    async def shutdown(self) -> None:
        """Convenience: current -> STOPPED."""
        await self.stop()
        self._transition(PluginState.STOPPED)

    # ---- Legacy SDK v1 helpers (setup-style plugins) ----

    def setup(self) -> None:
        """Hook for legacy plugins to declare routes, events, etc."""

    def register(self) -> None:
        """Legacy: mount router on host app (SDK v1 style).

        Calls setup() first (if overridden), then includes the router.
        Checks both self.router and self._router for compatibility.
        """
        # Call setup() if the subclass overrides it (legacy pattern)
        if type(self).setup is not PluginBase.setup:
            self.setup()

        router = getattr(self, "router", None) or getattr(self, "_router", None)
        if self.app is not None and hasattr(self.app, "include_router") and router is not None:
            self.app.include_router(router)
        import logging

        logging.getLogger(__name__).info("plugin %s registered", self.name)


# Legacy alias kept for core/plugin_manager/hooks.py TYPE_CHECKING use.
DDWPlugin = PluginBase


@dataclass
class PluginContext:
    """Legacy plugin load context (SDK v1)."""

    loaded_plugins: list[Any] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)


class LegacyPluginBase(PluginBase):
    """Explicit legacy alias (SDK v1 interface). Deprecated."""


# ---------------------------------------------------------------------------
# SDK helpers: ExecutionTrace
# ---------------------------------------------------------------------------


class ExecutionTrace:
    """Async context manager that records a single Span.

    The trace is *in-memory* by default; consumers (e.g. ``ddw-trace-panel``)
    can read the public attributes after the ``async with`` block exits.

    Attributes:
        trace_id: W3C-style 32-hex trace identifier.
        span_id: W3C-style 16-hex span identifier.
        parent_span_id: Optional parent span identifier.
        plugin_name: Owning plugin name.
        operation: Operation label (e.g. ``"semantic_search"``).
        start_time: UTC datetime when the span was opened.
        end_time: UTC datetime when the span was closed (``None`` until exit).
        status: ``"ok"`` or ``"error"``.
        status_message: Optional human-readable error/notes.
        attributes: Free-form JSON-serialisable metadata.
        duration_ms: Computed on exit, in milliseconds.
    """

    def __init__(
        self,
        plugin_name: str,
        operation: str,
        trace_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        attributes: Optional[dict[str, Any]] = None,
    ) -> None:
        self.trace_id: str = trace_id or uuid.uuid4().hex
        self.span_id: str = uuid.uuid4().hex[:16]
        self.parent_span_id: Optional[str] = parent_span_id
        self.plugin_name: str = plugin_name
        self.operation: str = operation
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.status: str = "ok"
        self.status_message: Optional[str] = None
        self.attributes: dict[str, Any] = dict(attributes or {})
        self.duration_ms: Optional[int] = None
        self._monotonic_start: Optional[float] = None

    async def __aenter__(self) -> "ExecutionTrace":
        self.start_time = datetime.now(timezone.utc)
        self._monotonic_start = time.monotonic()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        end = datetime.now(timezone.utc)
        self.end_time = end
        if self._monotonic_start is not None:
            self.duration_ms = int((time.monotonic() - self._monotonic_start) * 1000)
        if exc_type is not None:
            self.status = "error"
            self.status_message = str(exc_val) if exc_val else exc_type.__name__
        else:
            self.status = "ok"

    def to_dict(self) -> dict[str, Any]:
        """Serialise the span to a JSON-friendly dict."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "plugin_name": self.plugin_name,
            "operation": self.operation,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status,
            "status_message": self.status_message,
            "attributes": self.attributes,
            "duration_ms": self.duration_ms,
        }


# ---------------------------------------------------------------------------
# SDK helpers: InterventionHooks
# ---------------------------------------------------------------------------


BeforeHook = Callable[[dict[str, Any]], Awaitable[None]]
AfterHook = Callable[[dict[str, Any]], Awaitable[None]]


class InterventionHooks:
    """Registry of async before/after hooks for cross-cutting intervention flows.

    Plugins that need to coordinate with feedback-driven interventions
    (``ddw-feedback-loop``) can register callbacks here without taking
    a hard dependency on the feedback plugin.

    Example:
        >>> hooks = InterventionHooks()
        >>> @hooks.on_before_call
        ... async def log_call(ctx): ...
    """

    def __init__(self) -> None:
        self._before_hooks: list[BeforeHook] = []
        self._after_hooks: list[AfterHook] = []

    def on_before_call(self, hook: BeforeHook) -> BeforeHook:
        """Register a before-call hook (decorator-style)."""
        self._before_hooks.append(hook)
        return hook

    def on_after_call(self, hook: AfterHook) -> AfterHook:
        """Register an after-call hook (decorator-style)."""
        self._after_hooks.append(hook)
        return hook

    def add_before(self, hook: BeforeHook) -> None:
        self._before_hooks.append(hook)

    def add_after(self, hook: AfterHook) -> None:
        self._after_hooks.append(hook)

    async def run_before(self, context: dict[str, Any]) -> None:
        for hook in list(self._before_hooks):
            await hook(context)

    async def run_after(self, context: dict[str, Any]) -> None:
        for hook in list(self._after_hooks):
            await hook(context)


# ---------------------------------------------------------------------------
# Convenience context manager that pairs a plugin with an ExecutionTrace
# ---------------------------------------------------------------------------


@asynccontextmanager
async def traced_operation(
    plugin_name: str,
    operation: str,
    *,
    attributes: Optional[dict[str, Any]] = None,
    parent_span_id: Optional[str] = None,
):
    """Sugar for ``async with ExecutionTrace(...) as span: ...``.

    Yields the :class:`ExecutionTrace` so callers can mutate attributes
    or status mid-flight.
    """
    trace = ExecutionTrace(
        plugin_name=plugin_name,
        operation=operation,
        attributes=attributes,
        parent_span_id=parent_span_id,
    )
    async with trace as span:
        yield span
