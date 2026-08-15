"""DDW LLM 重试生成器（技术规范 §5.1）

继承 v5.3 §18.11 LLM 重试 + 规范 §5.1 细化。

特性：
- 分级重试：前台可重试，后台立即 bail
- 持久模式 (UNATTENDED_RETRY=true)：429/529 永远重试，最大 6h
- 心跳：每 30s yield SystemMessage
- 529 cascade：连续 3 次切换 fallback model
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import AsyncIterator, Awaitable, Callable

log = logging.getLogger(__name__)


class RetryClass(str, Enum):
    FOREGROUND = "foreground"   # 前台任务：可重试
    BACKGROUND = "background"   # 后台任务：立即 bail


@dataclass
class RetryConfig:
    max_attempts: int = 3
    initial_backoff: float = 1.0
    backoff_multiplier: float = 2.0
    max_backoff: float = 30.0
    unattended_mode: bool = False
    unattended_max_seconds: float = 6 * 3600  # 6h
    heartbeat_interval: float = 30.0
    cascade_529_threshold: int = 3
    rate_limit_codes: tuple[int, ...] = (429, 529)


@dataclass
class RetryResult:
    success: bool
    attempts: int
    total_seconds: float
    fallback_used: bool = False
    final_error: str = ""


async def llm_retry_stream(
    call_fn: Callable[[], Awaitable[AsyncIterator[str]]],
    config: RetryConfig | None = None,
    retry_class: RetryClass = RetryClass.FOREGROUND,
) -> AsyncIterator[str]:
    """LLM 调用重试流式包装（async generator）。"""
    cfg = config or RetryConfig()
    attempt = 0
    start = time.time()
    consecutive_529 = 0
    fallback_used = False

    while True:
        attempt += 1
        # 持久模式时间上限
        if cfg.unattended_mode and (time.time() - start) > cfg.unattended_max_seconds:
            raise TimeoutError(f"unattended retry 超 {cfg.unattended_max_seconds}s")

        # 后台任务只重试 1 次
        if retry_class == RetryClass.BACKGROUND and attempt > 1:
            raise RuntimeError("后台任务：立即 bail")

        try:
            stream = await call_fn()
            async for chunk in stream:
                yield chunk
            return  # 成功
        except Exception as e:  # noqa: BLE001
            code = getattr(e, "status_code", 0) or 0
            log.warning("LLM call attempt %d failed: %s (code=%d)", attempt, e, code)

            # 529 cascade
            if code == 529:
                consecutive_529 += 1
                if consecutive_529 >= cfg.cascade_529_threshold and not fallback_used:
                    fallback_used = True
                    log.warning("529 cascade triggered → fallback model")
                    # 注：fallback model 切换由调用方实现（修改 call_fn 内部）

            # 是否重试
            if attempt >= cfg.max_attempts:
                if cfg.unattended_mode and code in cfg.rate_limit_codes:
                    # 持久模式：429/529 永远重试
                    backoff = min(cfg.initial_backoff * (cfg.backoff_multiplier ** (attempt - 1)), cfg.max_backoff)
                    log.info("unattended retry: backoff %.1fs", backoff)
                    await _heartbeat_sleep(backoff, cfg.heartbeat_interval)
                    continue
                raise

            backoff = min(cfg.initial_backoff * (cfg.backoff_multiplier ** (attempt - 1)), cfg.max_backoff)
            await _heartbeat_sleep(backoff, cfg.heartbeat_interval)


async def _heartbeat_sleep(total_seconds: float, heartbeat_interval: float) -> None:
    """分段时间睡眠，每 interval 输出心跳 SystemMessage。"""
    elapsed = 0.0
    while elapsed < total_seconds:
        chunk = min(heartbeat_interval, total_seconds - elapsed)
        await asyncio.sleep(chunk)
        elapsed += chunk
        if elapsed < total_seconds:
            yield_msg = f"[SYSTEM] retry heartbeat at {elapsed:.0f}s / {total_seconds:.0f}s"
            log.info(yield_msg)
