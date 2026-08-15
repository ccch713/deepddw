"""
健康检查端点测试

覆盖:
- ChannelHealthMonitor.get_health_summary()
- 空渠道时返回
- 有渠道时返回状态/延迟/错误率
- /health 端点集成
"""
from __future__ import annotations

from ddw_llm_gateway.circuit_breaker import CircuitBreaker
from ddw_llm_gateway.health_monitor import ChannelHealthMonitor


class _FakeChannelManager:
    """测试用渠道管理器"""

    def __init__(self, channels=None):
        self._channels = channels or []

    def list_all(self):
        return self._channels


class _FakeChannel:
    """测试用渠道"""

    def __init__(self, id, name, status=1, response_time=100):
        self.id = id
        self.name = name
        self.status = status
        self.response_time = response_time


class TestHealthSummary:
    """get_health_summary 测试"""

    def test_empty_channels(self):
        """无渠道时返回空摘要"""
        cm = _FakeChannelManager()
        cb = CircuitBreaker()
        monitor = ChannelHealthMonitor(channel_manager=cm, circuit_breaker=cb)
        summary = monitor.get_health_summary()
        assert summary["status"] == "degraded"
        assert summary["summary"]["total_channels"] == 0
        assert summary["channels"] == []

    def test_enabled_channels(self):
        """有启用渠道时返回 healthy"""
        cm = _FakeChannelManager(channels=[
            _FakeChannel(id=1, name="ch1", status=1, response_time=100),
            _FakeChannel(id=2, name="ch2", status=1, response_time=200),
        ])
        cb = CircuitBreaker()
        monitor = ChannelHealthMonitor(channel_manager=cm, circuit_breaker=cb)
        summary = monitor.get_health_summary()
        assert summary["status"] == "healthy"
        assert summary["summary"]["total_channels"] == 2
        assert summary["summary"]["enabled"] == 2
        assert summary["summary"]["disabled"] == 0
        assert summary["summary"]["avg_response_time_ms"] == 150

    def test_all_disabled_channels(self):
        """全部禁用时返回 degraded"""
        cm = _FakeChannelManager(channels=[
            _FakeChannel(id=1, name="ch1", status=2),
            _FakeChannel(id=2, name="ch2", status=3),
        ])
        cb = CircuitBreaker()
        monitor = ChannelHealthMonitor(channel_manager=cm, circuit_breaker=cb)
        summary = monitor.get_health_summary()
        assert summary["status"] == "degraded"
        assert summary["summary"]["enabled"] == 0
        assert summary["summary"]["disabled"] == 2

    def test_channel_error_rate(self):
        """渠道错误率计算"""
        cm = _FakeChannelManager(channels=[
            _FakeChannel(id=1, name="ch1", status=1),
        ])
        cb = CircuitBreaker()
        # 8 次成功 + 2 次失败
        for _ in range(8):
            cb.record_success(1)
        for _ in range(2):
            cb.record_failure(1)
        monitor = ChannelHealthMonitor(channel_manager=cm, circuit_breaker=cb)
        summary = monitor.get_health_summary()
        ch = summary["channels"][0]
        assert ch["total_requests"] == 10
        assert ch["total_failures"] == 2
        assert ch["error_rate"] == 0.2
        assert ch["success_rate"] == 0.8

    def test_channel_status_names(self):
        """状态名称映射"""
        cm = _FakeChannelManager(channels=[
            _FakeChannel(id=1, name="ch1", status=0),
            _FakeChannel(id=2, name="ch2", status=1),
            _FakeChannel(id=3, name="ch3", status=2),
            _FakeChannel(id=4, name="ch4", status=3),
        ])
        cb = CircuitBreaker()
        monitor = ChannelHealthMonitor(channel_manager=cm, circuit_breaker=cb)
        summary = monitor.get_health_summary()
        statuses = {c["name"]: c["status"] for c in summary["channels"]}
        assert statuses["ch1"] == "unknown"
        assert statuses["ch2"] == "enabled"
        assert statuses["ch3"] == "manual_disabled"
        assert statuses["ch4"] == "auto_disabled"

    def test_summary_has_timestamp(self):
        """摘要包含时间戳"""
        cm = _FakeChannelManager()
        cb = CircuitBreaker()
        monitor = ChannelHealthMonitor(channel_manager=cm, circuit_breaker=cb)
        summary = monitor.get_health_summary()
        assert "timestamp" in summary
        assert summary["timestamp"] > 0

    def test_no_circuit_breaker(self):
        """无断路器时正常工作"""
        cm = _FakeChannelManager(channels=[
            _FakeChannel(id=1, name="ch1", status=1, response_time=50),
        ])
        monitor = ChannelHealthMonitor(channel_manager=cm, circuit_breaker=None)
        summary = monitor.get_health_summary()
        assert summary["summary"]["total_channels"] == 1
        ch = summary["channels"][0]
        assert ch["error_rate"] == 0.0
        assert ch["consecutive_failures"] == 0
