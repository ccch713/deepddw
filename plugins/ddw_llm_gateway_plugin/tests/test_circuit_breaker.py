"""
断路器测试

覆盖:
- 成功/失败记录
- 连续失败自动禁用
- 成功率计算
- 重测时间检查
- 状态重置
"""
from __future__ import annotations

import time

import pytest
from ddw_llm_gateway.circuit_breaker import ChannelStatus, CircuitBreaker


class TestCircuitBreaker:
    """断路器测试"""

    def setup_method(self):
        """每个测试方法前初始化"""
        self.cb = CircuitBreaker(
            disable_threshold=3,
            retest_interval=1,  # 1秒（测试用）
            success_rate_threshold=0.5,
        )

    def test_record_success(self):
        """记录成功请求"""
        self.cb.record_success(1)
        health = self.cb.get_health(1)
        assert health.total_requests == 1
        assert health.consecutive_failures == 0
        assert health.status == ChannelStatus.ENABLED

    def test_record_failure(self):
        """记录失败请求"""
        self.cb.record_failure(1)
        health = self.cb.get_health(1)
        assert health.total_requests == 1
        assert health.total_failures == 1
        assert health.consecutive_failures == 1

    def test_auto_disable_on_consecutive_failures(self):
        """连续失败达到阈值自动禁用"""
        for _ in range(3):
            self.cb.record_failure(1)

        health = self.cb.get_health(1)
        assert health.status == ChannelStatus.AUTO_DISABLED
        assert health.consecutive_failures == 3
        assert health.auto_disabled_at > 0

    def test_success_resets_consecutive_failures(self):
        """成功重置连续失败计数"""
        self.cb.record_failure(1)
        self.cb.record_failure(1)
        self.cb.record_success(1)  # 成功重置

        health = self.cb.get_health(1)
        assert health.consecutive_failures == 0

    def test_auto_disable_recover_on_success(self):
        """自动禁用后成功恢复"""
        for _ in range(3):
            self.cb.record_failure(1)

        self.cb.record_success(1)

        health = self.cb.get_health(1)
        assert health.status == ChannelStatus.ENABLED

    def test_should_retry_enabled(self):
        """启用渠道可以重试"""
        assert self.cb.should_retry(1) is True

    def test_should_retry_disabled(self):
        """禁用渠道不能重试"""
        for _ in range(3):
            self.cb.record_failure(1)
        assert self.cb.should_retry(1) is False

    def test_should_retest_not_disabled(self):
        """未禁用渠道不需要重测"""
        assert self.cb.should_retest(1) is False

    def test_should_retest_disabled_too_soon(self):
        """禁用渠道未到重测时间"""
        for _ in range(3):
            self.cb.record_failure(1)
        # 刚禁用，还没到重测时间
        assert self.cb.should_retest(1) is False

    def test_should_retest_ready(self):
        """禁用渠道到了重测时间"""
        for _ in range(3):
            self.cb.record_failure(1)
        # 等待重测间隔
        time.sleep(1.1)
        assert self.cb.should_retest(1) is True

    def test_get_success_rate_no_requests(self):
        """无请求时成功率返回 1.0"""
        assert self.cb.get_success_rate(1) == 1.0

    def test_get_success_rate(self):
        """计算成功率"""
        self.cb.record_success(1)
        self.cb.record_success(1)
        self.cb.record_failure(1)

        rate = self.cb.get_success_rate(1)
        assert rate == pytest.approx(2.0 / 3.0, abs=0.01)

    def test_get_channels_needing_retest(self):
        """获取需要重测的渠道列表"""
        for _ in range(3):
            self.cb.record_failure(1)

        time.sleep(1.1)

        needing = self.cb.get_channels_needing_retest()
        assert 1 in needing

    def test_disable_channel_manual(self):
        """手动禁用渠道"""
        self.cb.disable_channel(1, reason="manual")
        health = self.cb.get_health(1)
        assert health.status == ChannelStatus.MANUAL_DISABLED
        assert health.disabled_by == "manual"

    def test_enable_channel(self):
        """启用渠道"""
        self.cb.disable_channel(1)
        self.cb.enable_channel(1)
        health = self.cb.get_health(1)
        assert health.status == ChannelStatus.ENABLED

    def test_reset(self):
        """重置渠道健康状态"""
        self.cb.record_failure(1)
        self.cb.record_failure(1)
        self.cb.reset(1)

        health = self.cb.get_health(1)
        assert health.consecutive_failures == 0
        assert health.total_requests == 0
        assert health.status == ChannelStatus.ENABLED

    def test_get_all_health(self):
        """获取所有渠道健康状态"""
        self.cb.record_success(1)
        self.cb.record_failure(2)

        all_health = self.cb.get_all_health()
        assert 1 in all_health
        assert 2 in all_health
        assert all_health[1].total_requests == 1
        assert all_health[2].total_failures == 1
