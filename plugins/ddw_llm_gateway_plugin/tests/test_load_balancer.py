"""
负载均衡器测试

覆盖:
- 三阶段筛选逻辑
- 优先级分组
- 加权随机
- 成功率过滤
- ignore_first_priority
"""
from __future__ import annotations

from ddw_llm_gateway.load_balancer import ChannelCandidate, LoadBalancer


class TestLoadBalancer:
    """负载均衡器测试"""

    def setup_method(self):
        """每个测试方法前初始化"""
        self.lb = LoadBalancer(success_rate_threshold=0.5)

    def test_select_single_candidate(self):
        """单个候选渠道 → 直接返回"""
        candidates = [
            ChannelCandidate(id=1, name="ch1", priority=10, weight=100,
                           response_time=100, balance=10.0, success_rate=1.0),
        ]
        result = self.lb.select(candidates)
        assert result is not None
        assert result.id == 1

    def test_select_empty_candidates(self):
        """空候选列表 → 返回 None"""
        result = self.lb.select([])
        assert result is None

    def test_select_filters_low_success_rate(self):
        """低成功率渠道被过滤"""
        candidates = [
            ChannelCandidate(id=1, name="ch1", priority=10, weight=100,
                           response_time=100, balance=10.0, success_rate=0.3),  # 低于阈值
            ChannelCandidate(id=2, name="ch2", priority=5, weight=50,
                           response_time=200, balance=10.0, success_rate=1.0),
        ]
        result = self.lb.select(candidates)
        assert result is not None
        assert result.id == 2  # ch1 被过滤

    def test_select_filters_zero_balance(self):
        """余额为 0 的渠道被过滤"""
        candidates = [
            ChannelCandidate(id=1, name="ch1", priority=10, weight=100,
                           response_time=100, balance=0.0, success_rate=1.0),
            ChannelCandidate(id=2, name="ch2", priority=5, weight=50,
                           response_time=200, balance=5.0, success_rate=1.0),
        ]
        result = self.lb.select(candidates)
        assert result is not None
        assert result.id == 2  # ch1 余额为 0 被过滤

    def test_select_negative_balance_allowed(self):
        """负余额（无限额度）渠道被保留"""
        candidates = [
            ChannelCandidate(id=1, name="ch1", priority=10, weight=100,
                           response_time=100, balance=-1.0, success_rate=1.0),
        ]
        result = self.lb.select(candidates)
        assert result is not None
        assert result.id == 1

    def test_select_highest_priority(self):
        """选择最高优先级渠道"""
        candidates = [
            ChannelCandidate(id=1, name="ch1", priority=5, weight=100,
                           response_time=100, balance=10.0, success_rate=1.0),
            ChannelCandidate(id=2, name="ch2", priority=10, weight=50,
                           response_time=200, balance=10.0, success_rate=1.0),
            ChannelCandidate(id=3, name="ch3", priority=1, weight=100,
                           response_time=50, balance=10.0, success_rate=1.0),
        ]
        result = self.lb.select(candidates)
        assert result is not None
        assert result.id == 2  # 最高优先级

    def test_select_weighted_random(self):
        """同优先级内加权随机"""
        candidates = [
            ChannelCandidate(id=1, name="ch1", priority=10, weight=100,
                           response_time=100, balance=10.0, success_rate=1.0),
            ChannelCandidate(id=2, name="ch2", priority=10, weight=1,
                           response_time=100, balance=10.0, success_rate=1.0),
        ]
        # 运行多次，统计选择次数
        counts = {1: 0, 2: 0}
        for _ in range(1000):
            result = self.lb.select(candidates)
            if result:
                counts[result.id] += 1

        # ch1 权重高，应该被选择更多次
        assert counts[1] > counts[2]

    def test_select_ignore_first_priority(self):
        """ignore_first_priority 跳过最高优先级"""
        candidates = [
            ChannelCandidate(id=1, name="ch1", priority=10, weight=100,
                           response_time=100, balance=10.0, success_rate=1.0),
            ChannelCandidate(id=2, name="ch2", priority=5, weight=50,
                           response_time=200, balance=10.0, success_rate=1.0),
        ]
        result = self.lb.select(candidates, ignore_first_priority=True)
        assert result is not None
        assert result.id == 2  # 跳过最高优先级

    def test_select_by_model(self):
        """按模型过滤"""
        candidates = [
            ChannelCandidate(id=1, name="ch1", priority=10, weight=100,
                           response_time=100, balance=10.0, success_rate=1.0,
                           models=["gpt-4", "gpt-3.5-turbo"]),
            ChannelCandidate(id=2, name="ch2", priority=10, weight=100,
                           response_time=100, balance=10.0, success_rate=1.0,
                           models=["deepseek-chat"]),
        ]
        result = self.lb.select(candidates, model="gpt-4")
        assert result is not None
        assert result.id == 1

    def test_select_multiple(self):
        """选择多个渠道"""
        candidates = [
            ChannelCandidate(id=1, name="ch1", priority=10, weight=100,
                           response_time=100, balance=10.0, success_rate=1.0),
            ChannelCandidate(id=2, name="ch2", priority=10, weight=50,
                           response_time=200, balance=10.0, success_rate=1.0),
            ChannelCandidate(id=3, name="ch3", priority=5, weight=100,
                           response_time=300, balance=10.0, success_rate=1.0),
        ]
        result = self.lb.select_multiple(candidates, count=2)
        assert len(result) == 2
        # 两个都是最高优先级
        assert all(c.priority == 10 for c in result)

    def test_sort_by_priority(self):
        """按优先级排序"""
        candidates = [
            ChannelCandidate(id=1, name="ch1", priority=5, weight=100,
                           response_time=100, balance=10.0, success_rate=1.0),
            ChannelCandidate(id=2, name="ch2", priority=10, weight=50,
                           response_time=200, balance=10.0, success_rate=1.0),
            ChannelCandidate(id=3, name="ch3", priority=1, weight=100,
                           response_time=50, balance=10.0, success_rate=1.0),
        ]
        sorted_candidates = self.lb.sort_by_priority(candidates)
        assert sorted_candidates[0].id == 2  # 最高优先级
        assert sorted_candidates[-1].id == 3  # 最低优先级

    def test_sort_by_response_time(self):
        """按响应时间排序"""
        candidates = [
            ChannelCandidate(id=1, name="ch1", priority=10, weight=100,
                           response_time=300, balance=10.0, success_rate=1.0),
            ChannelCandidate(id=2, name="ch2", priority=10, weight=50,
                           response_time=100, balance=10.0, success_rate=1.0),
            ChannelCandidate(id=3, name="ch3", priority=10, weight=100,
                           response_time=200, balance=10.0, success_rate=1.0),
        ]
        sorted_candidates = self.lb.sort_by_response_time(candidates)
        assert sorted_candidates[0].id == 2  # 最快
        assert sorted_candidates[-1].id == 1  # 最慢


class TestSessionAffinity:
    """Session-Affinity 路由测试（Reasonix 模式）"""

    def setup_method(self):
        self.lb = LoadBalancer(success_rate_threshold=0.5)
        self.candidates = [
            ChannelCandidate(id=1, name="ch1", priority=10, weight=100,
                           response_time=100, balance=10.0, success_rate=1.0),
            ChannelCandidate(id=2, name="ch2", priority=5, weight=50,
                           response_time=200, balance=10.0, success_rate=1.0),
        ]

    def test_affinity_first_call_records_binding(self):
        """首次调用记录 session → channel 绑定"""
        result = self.lb.select_with_affinity(self.candidates, session_id="s1")
        assert result is not None
        # 第二次调用应返回同一 channel
        result2 = self.lb.select_with_affinity(self.candidates, session_id="s1")
        assert result2 is not None
        assert result2.id == result.id

    def test_affinity_no_session_fallback(self):
        """无 session_id 时退化为普通 select"""
        result = self.lb.select_with_affinity(self.candidates, session_id=None)
        assert result is not None
        assert result.id in (1, 2)

    def test_affinity_expired_fallback(self):
        """TTL 过期后重新选择"""
        # 使用极短 TTL
        result1 = self.lb.select_with_affinity(
            self.candidates, session_id="s2", affinity_ttl=0.0
        )
        assert result1 is not None
        # TTL=0 立即过期，下次重新选择
        result2 = self.lb.select_with_affinity(
            self.candidates, session_id="s2", affinity_ttl=0.0
        )
        assert result2 is not None

    def test_affinity_channel_removed_fallback(self):
        """绑定的 channel 不在候选列表时回退"""
        result1 = self.lb.select_with_affinity(self.candidates, session_id="s3")
        assert result1 is not None
        # 只保留一个不同的 channel
        single = [ChannelCandidate(id=99, name="ch99", priority=10, weight=100,
                                   response_time=50, balance=10.0, success_rate=1.0)]
        result2 = self.lb.select_with_affinity(single, session_id="s3")
        assert result2 is not None
        assert result2.id == 99  # 回退到新 channel

    def test_clear_affinity(self):
        """清除亲和性后重新选择"""
        result1 = self.lb.select_with_affinity(self.candidates, session_id="s4")
        assert result1 is not None
        self.lb.clear_affinity("s4")
        # 清除后可以选不同 channel（取决于随机权重）
        result2 = self.lb.select_with_affinity(self.candidates, session_id="s4")
        assert result2 is not None

    def test_affinity_filters_low_success_rate(self):
        """亲和性 channel 成功率低于阈值时回退"""
        bad = ChannelCandidate(id=1, name="ch1", priority=10, weight=100,
                              response_time=100, balance=10.0, success_rate=0.3)
        good = ChannelCandidate(id=2, name="ch2", priority=5, weight=50,
                               response_time=200, balance=10.0, success_rate=1.0)
        # 先绑定到 ch2（成功率合格）
        self.lb._session_affinity["s5"] = (2, __import__("time").monotonic())
        result = self.lb.select_with_affinity([bad, good], session_id="s5")
        assert result is not None
        assert result.id == 2
