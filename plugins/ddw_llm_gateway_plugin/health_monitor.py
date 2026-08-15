"""
渠道健康监控后台任务

映射源: One API controller/channel-test.go:AutomaticallyTestChannels()
        (goroutine, 每 N 秒扫描一次)

流程:
1. 每 retest_interval 秒扫描所有渠道
2. AUTO_DISABLED 渠道 → 发送测试请求
3. 测试成功 → 恢复 ENABLED
4. 测试失败 → 保持 AUTO_DISABLED，重置计时
5. ENABLED 渠道连续失败 → 自动禁用
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import httpx

from .circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class ChannelHealthMonitor:
    """
    渠道健康监控 — 定时测试 + 自动禁用/启用

    映射: controller/channel-test.go:AutomaticallyTestChannels()

    流程:
    1. 每 retest_interval 秒扫描所有渠道
    2. AUTO_DISABLED 渠道 → 发送测试请求
    3. 测试成功 → 恢复 ENABLED
    4. 测试失败 → 保持 AUTO_DISABLED，重置计时
    5. ENABLED 渠道连续失败 → 自动禁用
    """

    def __init__(
        self,
        channel_manager: Any | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        retest_interval: int = 300,
    ):
        """
        初始化健康监控

        Args:
            channel_manager: 渠道管理器
            circuit_breaker: 断路器
            retest_interval: 重测间隔（秒）
        """
        self._channel_manager = channel_manager
        self._circuit_breaker = circuit_breaker
        self._retest_interval = retest_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._http_client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        """启动后台监控"""
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("渠道健康监控已启动，间隔 %d 秒", self._retest_interval)

    async def stop(self) -> None:
        """停止后台监控"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
        logger.info("渠道健康监控已停止")

    async def _monitor_loop(self) -> None:
        """监控主循环"""
        while self._running:
            try:
                await self._scan_channels()
            except Exception as e:
                logger.error("渠道扫描异常: %s", e)
            await asyncio.sleep(self._retest_interval)

    async def _scan_channels(self) -> None:
        """扫描所有渠道，测试需要重测的"""
        if not self._channel_manager or not self._circuit_breaker:
            return

        channels = await self._channel_manager.list_all()
        for channel in channels:
            if self._circuit_breaker.should_retest(channel.id):
                await self._test_channel(channel)

    async def _test_channel(self, channel: Any) -> None:
        """测试单个渠道"""
        try:
            success = await self._ping_channel(channel)
            if success:
                self._circuit_breaker.record_success(channel.id)
                # 恢复渠道状态
                if self._channel_manager:
                    await self._channel_manager.enable(channel.id)
                logger.info(
                    "渠道 %s (%d) 测试通过，恢复启用",
                    channel.name, channel.id
                )
            else:
                self._circuit_breaker.record_failure(channel.id)
                logger.warning(
                    "渠道 %s (%d) 测试失败",
                    channel.name, channel.id
                )
        except Exception as e:
            self._circuit_breaker.record_failure(channel.id)
            logger.error(
                "渠道 %s (%d) 测试异常: %s",
                channel.name, channel.id, e
            )

    async def _ping_channel(self, channel: Any) -> bool:
        """
        发送轻量级 ping 测试

        实际实现：发送 GET /v1/models 或最小 POST 请求
        """
        try:
            client = await self._get_http_client()
            url = f"{channel.base_url}/v1/models"
            response = await client.get(url, timeout=10.0)
            return response.status_code == 200
        except Exception:
            return False

    async def _get_http_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端"""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient()
        return self._http_client

    async def test_single_channel(self, channel_id: int) -> dict:
        """
        手动测试单个渠道

        Args:
            channel_id: 渠道 ID

        Returns:
            测试结果字典
        """
        if not self._channel_manager:
            return {"success": False, "error": "渠道管理器未初始化"}

        channel = await self._channel_manager.get(channel_id)
        if not channel:
            return {"success": False, "error": f"渠道 {channel_id} 不存在"}

        start_time = time.time()
        success = await self._ping_channel(channel)
        response_time = int((time.time() - start_time) * 1000)

        return {
            "success": success,
            "channel_id": channel_id,
            "channel_name": channel.name,
            "response_time": response_time,
        }

    async def test_all_channels(self) -> list[dict]:
        """
        批量测试所有渠道

        Returns:
            测试结果列表
        """
        if not self._channel_manager:
            return []

        channels = await self._channel_manager.list_all()
        results = []
        for channel in channels:
            result = await self.test_single_channel(channel.id)
            results.append(result)

        return results

    def get_health_summary(self) -> dict:
        """
        获取所有渠道的健康摘要

        Returns:
            包含各渠道状态、延迟、错误率的字典
        """
        channels = []
        if self._channel_manager:
            for ch in self._channel_manager.list_all():
                health = None
                if self._circuit_breaker:
                    health = self._circuit_breaker.get_health(ch.id)

                total = health.total_requests if health else 0
                failures = health.total_failures if health else 0
                error_rate = round(failures / total, 4) if total > 0 else 0.0
                status_name = {
                    0: "unknown",
                    1: "enabled",
                    2: "manual_disabled",
                    3: "auto_disabled",
                }.get(ch.status, "unknown")

                channels.append({
                    "id": ch.id,
                    "name": ch.name,
                    "status": status_name,
                    "response_time_ms": ch.response_time,
                    "total_requests": total,
                    "total_failures": failures,
                    "error_rate": error_rate,
                    "success_rate": round(1.0 - error_rate, 4),
                    "consecutive_failures": health.consecutive_failures if health else 0,
                })

        total_channels = len(channels)
        enabled = sum(1 for c in channels if c["status"] == "enabled")
        avg_response = (
            sum(c["response_time_ms"] for c in channels) // total_channels
            if total_channels > 0 else 0
        )

        return {
            "status": "healthy" if enabled > 0 else "degraded",
            "timestamp": int(time.time()),
            "summary": {
                "total_channels": total_channels,
                "enabled": enabled,
                "disabled": total_channels - enabled,
                "avg_response_time_ms": avg_response,
            },
            "channels": channels,
        }
