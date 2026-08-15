"""DDW 分段式信号关闭（技术规范 §7.2 + SDK §7.2）

三段式：SIGINT → SIGTERM → SIGKILL。
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys

log = logging.getLogger(__name__)

# macOS 不支持 SIGINT 在所有进程，Linux 支持；这里用 SIGTERM 优先
if sys.platform == "darwin":
    _STAGE1 = signal.SIGTERM
    _STAGE1_WAIT = 0.1
    _STAGE2 = signal.SIGKILL
    _STAGE2_WAIT = 0.4
    _STAGE3_WAIT = 0.6
else:
    _STAGE1 = signal.SIGINT
    _STAGE1_WAIT = 0.1
    _STAGE2 = signal.SIGTERM
    _STAGE2_WAIT = 0.4
    _STAGE3 = signal.SIGKILL
    _STAGE3_WAIT = 0.6


def graceful_shutdown_plugin(process: subprocess.Popen) -> None:
    """三段式信号升级关闭子进程。

    Args:
        process: subprocess.Popen 实例
    """
    if process.poll() is not None:
        return  # 已退出

    # Stage 1
    try:
        process.send_signal(_STAGE1)
        process.wait(timeout=_STAGE1_WAIT)
        return
    except (subprocess.TimeoutExpired, OSError):
        pass

    # Stage 2
    try:
        process.send_signal(_STAGE2)
        process.wait(timeout=_STAGE2_WAIT)
        return
    except (subprocess.TimeoutExpired, OSError):
        pass

    # Stage 3: SIGKILL failsafe
    try:
        process.kill()
        process.wait(timeout=_STAGE3_WAIT)
    except subprocess.TimeoutExpired:
        # 硬杀
        try:
            os.kill(process.pid, signal.SIGKILL)
        except OSError as e:
            log.error("Hard kill failed for PID %d: %s", process.pid, e)


async def graceful_shutdown_plugin_async(process: subprocess.Popen) -> None:
    """异步版本。"""
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, graceful_shutdown_plugin, process)
