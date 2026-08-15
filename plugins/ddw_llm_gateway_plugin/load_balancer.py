"""
负载均衡引擎 — 优先级 + 加权随机 + 成功率过滤 + Session-Affinity

映射源:
- One API middleware/distributor.go:Distribute()
- One API model/cache.go:CacheGetRandomSatisfiedChannel()

三阶段筛选:
1. 按优先级分组（priority 从高到低）
2. 同优先级内按加权随机（weight 权重）
3. 成功率 > 阈值 + 余额 > 0 过滤

扩展: Session-Affinity 路由（Reasonix 模式）
- 同一 session_id 的连续请求优先路由到同一 channel
- 利用 DeepSeek prefix cache 降低 token 消耗
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class ChannelCandidate:
    """
    渠道候选（从缓存中筛选出的合格渠道）

    映射: One API model/cache.go 中的 channel 结构
    """
    id: int
    name: str
    priority: int
    weight: int
    response_time: int      # 毫秒
    balance: float          # USD 余额（-1 = 无限额度）
    success_rate: float     # 0.0 ~ 1.0
    models: list[str] | None = None  # 支持的模型列表

    def supports_model(self, model: str) -> bool:
        """检查是否支持指定模型"""
        if not self.models:
            return True  # 未指定模型列表 = 支持所有模型
        return model in self.models


class LoadBalancer:
    """
    渠道负载均衡器

    三阶段筛选:
    1. 按优先级分组（priority 从高到低）
    2. 同优先级内按加权随机（weight 权重）
    3. 成功率 > 阈值 + 余额 > 0 过滤

    映射: middleware/distributor.go:Distribute()
          model/cache.go:CacheGetRandomSatisfiedChannel()

    支持 ignore_first_priority: 重试时跳过最高优先级（避免重复使用失败渠道）
    支持 session_affinity: 同一 session 连续请求优先路由到同一 channel
    """

    # Session-affinity 状态映射: session_id -> (channel_id, last_seen_timestamp)
    _session_affinity: dict[str, tuple[int, float]]

    def __init__(self, success_rate_threshold: float = 0.5):
        """
        初始化负载均衡器

        Args:
            success_rate_threshold: 成功率阈值，低于此值的渠道被过滤
        """
        self._threshold = success_rate_threshold
        self._session_affinity = {}

    def select(
        self,
        candidates: list[ChannelCandidate],
        model: str = "",
        ignore_first_priority: bool = False,
    ) -> Optional[ChannelCandidate]:
        """
        从候选列表中选择一个渠道

        Args:
            candidates: 合格渠道列表
            model: 请求的模型名（用于过滤支持该模型的渠道）
            ignore_first_priority: 重试时跳过最高优先级

        Returns:
            选中的渠道，或 None（无可用渠道时）
        """
        if not candidates:
            return None

        # Step 1: 基础过滤
        eligible = [
            c for c in candidates
            if (c.success_rate >= self._threshold
                and (c.balance > 0 or c.balance < 0)  # balance < 0 = 无限额度
                and c.id > 0)
        ]

        # Step 2: 模型过滤
        if model:
            eligible = [c for c in eligible if c.supports_model(model)]

        if not eligible:
            return None

        # Step 3: 按优先级分组
        max_priority = max(c.priority for c in eligible)
        top_tier = [c for c in eligible if c.priority == max_priority]

        # Step 4: 忽略最高优先级（重试场景）
        if ignore_first_priority and len(eligible) > len(top_tier):
            # 选择次高优先级
            remaining = [c for c in eligible if c.priority < max_priority]
            if remaining:
                next_max = max(c.priority for c in remaining)
                top_tier = [c for c in remaining if c.priority == next_max]

        if not top_tier:
            return None

        # Step 5: 加权随机选择
        if len(top_tier) == 1:
            return top_tier[0]

        weights = [max(c.weight, 1) for c in top_tier]
        return random.choices(top_tier, weights=weights, k=1)[0]

    def select_with_affinity(
        self,
        candidates: list[ChannelCandidate],
        model: str = "",
        session_id: str | None = None,
        affinity_ttl: float = 300.0,
    ) -> Optional[ChannelCandidate]:
        """
        带 Session-Affinity 的渠道选择（Reasonix 模式）

        同一 session_id 的连续请求优先路由到同一 channel，
        利用 DeepSeek prefix cache 降低 token 消耗。

        Args:
            candidates: 合格渠道列表
            model: 请求的模型名
            session_id: 会话 ID（为 None 时退化为普通 select）
            affinity_ttl: 亲和性存活时间（秒），超时自动失效

        Returns:
            选中的渠道，或 None（无可用渠道时）
        """
        if not session_id:
            return self.select(candidates, model)

        # 查找已有亲和性记录
        affinity = self._session_affinity.get(session_id)
        if affinity is not None:
            pinned_channel_id, last_seen = affinity
            # 检查 TTL 是否过期
            if (time.monotonic() - last_seen) <= affinity_ttl:
                # 在候选列表中查找匹配的渠道
                for c in candidates:
                    if (c.id == pinned_channel_id
                            and c.success_rate >= self._threshold
                            and (c.balance > 0 or c.balance < 0)
                            and c.id > 0
                            and (not model or c.supports_model(model))):
                        # 更新 last_seen 并返回
                        self._session_affinity[session_id] = (c.id, time.monotonic())
                        return c
                # pinned channel 不在候选列表中，清除亲和性并回退
                del self._session_affinity[session_id]

        # 无亲和性或已失效：正常选择并记录
        selected = self.select(candidates, model)
        if selected is not None:
            self._session_affinity[session_id] = (selected.id, time.monotonic())
        return selected

    def clear_affinity(self, session_id: str) -> None:
        """
        清除指定 session 的亲和性绑定（会话结束时调用）

        Args:
            session_id: 要清除亲和性的会话 ID
        """
        self._session_affinity.pop(session_id, None)

    def select_multiple(
        self,
        candidates: list[ChannelCandidate],
        model: str = "",
        count: int = 1,
        ignore_first_priority: bool = False,
    ) -> list[ChannelCandidate]:
        """
        选择多个渠道（用于批量请求）

        Args:
            candidates: 合格渠道列表
            model: 请求的模型名
            count: 选择数量
            ignore_first_priority: 重试时跳过最高优先级

        Returns:
            选中的渠道列表
        """
        selected: list[ChannelCandidate] = []
        remaining = list(candidates)

        for _ in range(min(count, len(remaining))):
            channel = self.select(remaining, model, ignore_first_priority)
            if channel:
                selected.append(channel)
                remaining = [c for c in remaining if c.id != channel.id]
            else:
                break

        return selected

    def filter_by_model(
        self,
        candidates: list[ChannelCandidate],
        model: str,
    ) -> list[ChannelCandidate]:
        """筛选支持指定模型的渠道"""
        return [c for c in candidates if c.supports_model(model)]

    def sort_by_priority(
        self,
        candidates: list[ChannelCandidate],
    ) -> list[ChannelCandidate]:
        """按优先级降序排序"""
        return sorted(candidates, key=lambda c: c.priority, reverse=True)

    def sort_by_response_time(
        self,
        candidates: list[ChannelCandidate],
    ) -> list[ChannelCandidate]:
        """按响应时间升序排序（最快优先）"""
        return sorted(candidates, key=lambda c: c.response_time)
