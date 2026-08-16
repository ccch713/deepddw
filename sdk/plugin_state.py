"""DDW Plugin 5 态状态机（SDK v2 merged 2026-08-01）

继承 Plugin_SDK_接口规范 v1.0 §4.2（旧 5 态）：
    LOADING / ACTIVE / FAILED / DISABLED / NEEDS_UPDATE

新增 SDK v2 生命周期 5 态（与旧态共存）：
    CREATED / INITIALIZED / RUNNING / DEGRADED / STOPPED

两套状态共存以兼容旧插件（PluginStateInfo）与新插件（can_transition）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class PluginState(str, Enum):
    """Plugin 状态（P2-22 收敛：新 5 态为唯一主态；旧 5 态为兼容别名）。"""

    # ── SDK v2 生命周期（主态）──
    CREATED = "created"
    INITIALIZED = "initialized"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPED = "stopped"

    # ── SDK v1 兼容别名（映射到主态，避免 10 态混用）──
    LOADING = "initialized"
    ACTIVE = "running"
    FAILED = "degraded"
    DISABLED = "stopped"
    NEEDS_UPDATE = "running"

    @classmethod
    def is_terminal(cls, state: "PluginState") -> bool:
        """Return True if the state is a terminal state (no outbound transitions)."""
        return state == cls.STOPPED

    @classmethod
    def can_transition(cls, from_state: "PluginState", to_state: "PluginState") -> bool:
        """Validate whether a transition is allowed (SDK v2 lifecycle FSM).

        Only the new lifecycle states participate in this FSM; legacy
        states are treated as freely reachable for compatibility.
        """
        new_states = {cls.CREATED, cls.INITIALIZED, cls.RUNNING, cls.DEGRADED, cls.STOPPED}
        if from_state not in new_states:
            return True  # legacy states: no strict FSM
        allowed: dict[PluginState, set[PluginState]] = {
            cls.CREATED: {cls.INITIALIZED, cls.STOPPED},
            cls.INITIALIZED: {cls.RUNNING, cls.DEGRADED, cls.STOPPED},
            cls.RUNNING: {cls.DEGRADED, cls.STOPPED},
            cls.DEGRADED: {cls.RUNNING, cls.STOPPED},
            cls.STOPPED: set(),
        }
        return to_state in allowed.get(from_state, set())


@dataclass
class PluginStateInfo:
    """Plugin 状态详情（SDK v1，兼容）。"""

    state: PluginState
    name: str
    version: str

    # LOADING 期字段
    started_at: float = 0.0
    attempt_count: int = 0
    max_attempts: int = 5

    # FAILED 期字段
    error_code: int = 0          # 数字错误ID（不进日志文字）
    error_message: str = ""
    last_attempt_at: float = 0.0

    # ACTIVE 期字段
    capabilities: dict = field(default_factory=dict)
    loaded_at: float = 0.0

    # DISABLED 期字段
    disabled_by: str = ""        # "user" | "system" | "admin"
    reason: str = ""

    # NEEDS_UPDATE 期字段
    current_version: str = ""
    available_version: str = ""

    def to_loading(self) -> None:
        self.state = PluginState.LOADING
        self.started_at = time.time()
        self.attempt_count += 1
        self.last_attempt_at = self.started_at

    def to_active(self) -> None:
        self.state = PluginState.ACTIVE
        self.loaded_at = time.time()
        self.attempt_count = 0
        self.error_code = 0
        self.error_message = ""

    def to_failed(self, code: int, message: str) -> None:
        self.state = PluginState.FAILED
        self.error_code = code
        self.error_message = message
        self.last_attempt_at = time.time()

    def to_disabled(self, by: str, reason: str) -> None:
        self.state = PluginState.DISABLED
        self.disabled_by = by
        self.reason = reason

    def to_needs_update(self, available: str) -> None:
        self.state = PluginState.NEEDS_UPDATE
        self.current_version = self.version
        self.available_version = available

    def can_retry(self) -> bool:
        return self.attempt_count < self.max_attempts
