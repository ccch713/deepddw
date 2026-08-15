"""Plugin sandbox (PRD §18.7) — Phase 2 skeleton.

The sandbox hosts untrusted third-party plugins in a separate
process and exchanges JSON-RPC messages. Trusted plugins (the
``isolation: inline`` mode) do not use the sandbox; they are
imported directly.

This module provides:

* :class:`SandboxPolicy` — declarative policy
* :class:`JSONRPCBridge` — minimal JSON-RPC dispatcher (in-process stub)
* :func:`spawn_sandbox` — placeholder that uses ``subprocess`` to
  launch the plugin in isolation. Full process supervision lands
  in Phase 2 alongside the marketplace (PRD §12.2).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import signal
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SandboxPolicy:
    """Declarative policy applied to a sandboxed plugin."""

    name: str
    allow_network: bool = False
    allow_filesystem: bool = False
    cpu_limit_sec: int = 30
    memory_mb: int = 512
    env_allowlist: List[str] = field(default_factory=list)


@dataclass
class JSONRPCRequest:
    method: str
    params: Any = None
    id: Optional[str] = None


@dataclass
class JSONRPCResponse:
    result: Any = None
    error: Optional[str] = None
    id: Optional[str] = None


class JSONRPCBridge:
    """A tiny in-process JSON-RPC bridge for inline-style plugins.

    The bridge dispatches JSON-RPC method calls to registered
    Python callables. The wire format is JSON, one message per
    line. The bridge is symmetric — both the platform and the
    plugin can call each other.
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, Callable[[Any], Awaitable[Any]]] = {}

    def register(self, method: str, handler: Callable[[Any], Awaitable[Any]]) -> None:
        self._handlers[method] = handler

    async def handle_line(self, line: str) -> str:
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            return json.dumps(JSONRPCResponse(error=f"bad json: {exc}").__dict__, default=str)
        if "method" not in req:
            return json.dumps(JSONRPCResponse(error="missing method").__dict__, default=str)
        method = req["method"]
        handler = self._handlers.get(method)
        if handler is None:
            return json.dumps(JSONRPCResponse(error=f"unknown method: {method}", id=req.get("id")).__dict__, default=str)
        try:
            result = await handler(req.get("params"))
            return json.dumps(JSONRPCResponse(result=result, id=req.get("id")).__dict__, default=str)
        except Exception as exc:  # noqa: BLE001
            return json.dumps(JSONRPCResponse(error=str(exc), id=req.get("id")).__dict__, default=str)


# --------------------------------------------------------------------------- #
# Process sandbox (Phase 2 placeholder)
# --------------------------------------------------------------------------- #


async def spawn_sandbox(plugin_path: Path, policy: SandboxPolicy) -> int:
    """Launch ``plugin_path`` in a subprocess supervised by ``policy``.

    Returns the PID. In Phase 1 this is a thin wrapper around
    ``subprocess.Popen`` with basic isolation; a proper cgroup /
    namespace / seccomp policy lands in Phase 2.
    """

    if shutil.which("python3") is None:
        raise RuntimeError("python3 not found in PATH")
    env = {k: v for k, v in os.environ.items() if k in policy.env_allowlist}
    env["DDW_SANDBOX_NAME"] = policy.name
    env["DDW_SANDBOX_POLICY"] = json.dumps(policy.__dict__)
    cmd = [sys.executable, str(plugin_path)]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    logger.info("sandbox spawned pid=%s name=%s", proc.pid, policy.name)
    return proc.pid


def kill_sandbox(pid: int, sig: int = signal.SIGTERM) -> None:
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        pass
