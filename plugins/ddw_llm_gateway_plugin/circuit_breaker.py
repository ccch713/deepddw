"""
断路器 — 自动禁用/启用渠道

映射源:
- One API monitor/monitor.go:Emit() → 失败计数
- One API controller/channel-test.go:AutomaticallyTestChannels() → 定时测试

规则:
1. 连续失败 ≥ disable_threshold → 自动禁用渠道（AUTO_DISABLED）
2. 禁用后每 retest_interval 秒自动测试一次
3. 测试成功 → 恢复为 ENABLED
4. 成功率 = success / (success + failure)，低于阈值则降级
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import IntEnum

logger = logging.getLogger(__name__)


class ChannelStatus(IntEnum):
    """渠道状态 — 映射 One API model/channel.go Status"""
    UNKNOWN = 0
    ENABLED = 1
    MANUAL_DISABLED = 2
    AUTO_DISABLED = 3


@dataclass
class ChannelHealth:
    """渠道健康状态追踪"""
    channel_id: int
    status: ChannelStatus = ChannelStatus.ENABLED
    consecutive_failures: int = 0
    total_requests: int = 0
    total_failures: int = 0
    last_success_at: float = 0.0
    last_failure_at: float = 0.0
    auto_disabled_at: float = 0.0
    disabled_by: str = ""  # "auto" | "manual" | "system"


class CircuitBreaker:
    """
    渠道断路器 — 映射 One API monitor/monitor.go

    规则:
    1. 连续失败 ≥ disable_threshold → 自动禁用渠道（AUTO_DISABLED）
    2. 禁用后每 retest_interval 秒自动测试一次
    3. 测试成功 → 恢复为 ENABLED
    4. 成功率 = success / (success + failure)，低于阈值则降级

    对应 One API:
    - monitor.go:Emit() → 失败计数
    - controller/channel-test.go:AutomaticallyTestChannels() → 定时测试
    """

    def __init__(
        self,
        disable_threshold: int = 5,
        retest_interval: int = 300,
        success_rate_threshold: float = 0.5,
    ):
        """
        初始化断路器

        Args:
            disable_threshold: 连续失败阈值，达到后自动禁用
            retest_interval: 重测间隔（秒）
            success_rate_threshold: 成功率阈值，低于此值的渠道被过滤
        """
        self._disable_threshold = disable_threshold
        self._retest_interval = retest_interval
        self._success_rate_threshold = success_rate_threshold
        self._health: dict[int, ChannelHealth] = {}

    def record_success(self, channel_id: int) -> None:
        """
        记录成功请求

        对应 One API: monitor.go 中的成功计数逻辑
        """
        h = self._get_or_create(channel_id)
        h.consecutive_failures = 0
        h.total_requests += 1
        h.last_success_at = time.time()

        # 如果之前被自动禁用，恢复
        if h.status == ChannelStatus.AUTO_DISABLED:
            h.status = ChannelStatus.ENABLED
            h.disabled_by = ""
            logger.info("渠道 %d 恢复为启用状态", channel_id)

    def record_failure(self, channel_id: int) -> None:
        """
        记录失败请求

        对应 One API: monitor.go 中的失败计数 + 自动禁用逻辑
        """
        h = self._get_or_create(channel_id)
        h.consecutive_failures += 1
        h.total_requests += 1
        h.total_failures += 1
        h.last_failure_at = time.time()

        # 连续失败达到阈值 → 自动禁用
        if h.consecutive_failures >= self._disable_threshold:
            if h.status != ChannelStatus.AUTO_DISABLED:
                h.status = ChannelStatus.AUTO_DISABLED
                h.auto_disabled_at = time.time()
                h.disabled_by = "auto"
                logger.warning(
                    "渠道 %d 因连续 %d 次失败自动禁用",
                    channel_id, h.consecutive_failures
                )

    def should_retry(self, channel_id: int) -> bool:
        """检查渠道是否可以重试"""
        h = self._get_or_create(channel_id)
        return h.status == ChannelStatus.ENABLED

    def should_retest(self, channel_id: int) -> bool:
        """
        检查禁用渠道是否到了重测时间

        对应 One API: controller/channel-test.go:AutomaticallyTestChannels()
        """
        h = self._get_or_create(channel_id)
        if h.status != ChannelStatus.AUTO_DISABLED:
            return False
        if h.auto_disabled_at == 0:
            return False
        return (time.time() - h.auto_disabled_at) >= self._retest_interval

    def get_success_rate(self, channel_id: int) -> float:
        """
        获取成功率

        Returns:
            0.0 ~ 1.0 之间的成功率，未请求过返回 1.0
        """
        h = self._get_or_create(channel_id)
        if h.total_requests == 0:
            return 1.0
        return (h.total_requests - h.total_failures) / h.total_requests

    def get_health(self, channel_id: int) -> ChannelHealth:
        """获取渠道健康状态"""
        return self._get_or_create(channel_id)

    def get_all_health(self) -> dict[int, ChannelHealth]:
        """获取所有渠道的健康状态"""
        return dict(self._health)

    def reset(self, channel_id: int) -> None:
        """重置渠道的健康状态"""
        self._health[channel_id] = ChannelHealth(channel_id=channel_id)
        logger.info("渠道 %d 健康状态已重置", channel_id)

    def disable_channel(self, channel_id: int, reason: str = "manual") -> None:
        """手动禁用渠道"""
        h = self._get_or_create(channel_id)
        h.status = ChannelStatus.MANUAL_DISABLED
        h.disabled_by = reason
        logger.info("渠道 %d 已被 %s 禁用", channel_id, reason)

    def enable_channel(self, channel_id: int) -> None:
        """启用渠道"""
        h = self._get_or_create(channel_id)
        h.status = ChannelStatus.ENABLED
        h.consecutive_failures = 0
        h.disabled_by = ""
        logger.info("渠道 %d 已启用", channel_id)

    def get_channels_needing_retest(self) -> list[int]:
        """获取需要重测的渠道 ID 列表"""
        return [
            cid for cid, h in self._health.items()
            if h.status == ChannelStatus.AUTO_DISABLED
            and h.auto_disabled_at > 0
            and (time.time() - h.auto_disabled_at) >= self._retest_interval
        ]

    def _get_or_create(self, channel_id: int) -> ChannelHealth:
        """获取或创建渠道健康状态"""
        if channel_id not in self._health:
            self._health[channel_id] = ChannelHealth(channel_id=channel_id)
        return self._health[channel_id]
