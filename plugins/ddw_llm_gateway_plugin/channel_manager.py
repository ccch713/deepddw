"""
渠道管理器 — CRUD 操作 + 状态管理

映射源: One API model/channel.go + controller/channel.go
核心职责:
1. 渠道 CRUD（增删改查）
2. 状态管理（ENABLED/DISABLED/AUTO_DISABLED）
3. 渠道测试
4. 缓存预热
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from .channel_types import ChannelType, get_default_base_url
from .models import Channel

logger = logging.getLogger(__name__)


class ChannelStatus:
    """渠道状态常量 — 映射 One API model/channel.go Status"""
    UNKNOWN = 0
    ENABLED = 1
    MANUAL_DISABLED = 2
    AUTO_DISABLED = 3


class ChannelManager:
    """
    渠道管理器

    映射: One API model/channel.go + controller/channel.go

    功能:
    1. CRUD 操作（增删改查渠道）
    2. 状态管理（启用/禁用/自动禁用）
    3. 渠道筛选（按模型、分组、状态）
    4. 内存缓存（避免频繁查询数据库）
    """

    def __init__(self) -> None:
        self._channels: dict[int, Channel] = {}
        self._channel_counter: int = 0

    def create(
        self,
        name: str,
        channel_type: int,
        key: str,
        base_url: str = "",
        models: list[str] | None = None,
        priority: int = 0,
        weight: int = 0,
        group: str = "default",
        config: dict | None = None,
    ) -> Channel:
        """
        创建渠道

        Args:
            name: 渠道名称
            channel_type: 渠道类型（ChannelType 枚举值）
            key: API 密钥
            base_url: 基础 URL（空则使用默认值）
            models: 支持的模型列表
            priority: 优先级（越大越高）
            weight: 负载均衡权重
            group: 分组名称
            config: 渠道特定配置

        Returns:
            创建的 Channel 实例
        """
        self._channel_counter += 1
        channel_id = self._channel_counter

        if not base_url:
            base_url = get_default_base_url(channel_type)

        channel = Channel(
            id=channel_id,
            type=channel_type,
            name=name,
            key=key,
            status=ChannelStatus.ENABLED,
            weight=weight,
            priority=priority,
            base_url=base_url,
            models=",".join(models) if models else "",
            group=group,
            config=config or {},
            created_time=int(time.time()),
        )

        self._channels[channel_id] = channel
        logger.info("渠道已创建: %s (id=%d, type=%d)", name, channel_id, channel_type)
        return channel

    def get(self, channel_id: int) -> Optional[Channel]:
        """获取渠道"""
        return self._channels.get(channel_id)

    def update(
        self,
        channel_id: int,
        **kwargs,
    ) -> Optional[Channel]:
        """
        更新渠道

        Args:
            channel_id: 渠道 ID
            **kwargs: 要更新的字段

        Returns:
            更新后的 Channel 实例，或 None
        """
        channel = self._channels.get(channel_id)
        if not channel:
            logger.warning("渠道不存在: id=%d", channel_id)
            return None

        for key, value in kwargs.items():
            if hasattr(channel, key):
                setattr(channel, key, value)

        logger.info("渠道已更新: %s (id=%d)", channel.name, channel_id)
        return channel

    def delete(self, channel_id: int) -> bool:
        """
        删除渠道

        Returns:
            是否删除成功
        """
        if channel_id in self._channels:
            channel = self._channels.pop(channel_id)
            logger.info("渠道已删除: %s (id=%d)", channel.name, channel_id)
            return True
        logger.warning("渠道不存在: id=%d", channel_id)
        return False

    def list_all(self) -> list[Channel]:
        """获取所有渠道"""
        return list(self._channels.values())

    def list_enabled(self) -> list[Channel]:
        """获取所有启用的渠道"""
        return [
            ch for ch in self._channels.values()
            if ch.status == ChannelStatus.ENABLED
        ]

    def list_by_model(self, model: str) -> list[Channel]:
        """
        获取支持指定模型的所有启用渠道

        Args:
            model: 模型名称

        Returns:
            支持该模型的渠道列表
        """
        return [
            ch for ch in self._channels.values()
            if ch.status == ChannelStatus.ENABLED and ch.supports_model(model)
        ]

    def list_by_group(self, group: str) -> list[Channel]:
        """获取指定分组的所有渠道"""
        return [
            ch for ch in self._channels.values()
            if ch.group == group
        ]

    def set_status(self, channel_id: int, status: int) -> bool:
        """
        设置渠道状态

        Args:
            channel_id: 渠道 ID
            status: 新状态（ChannelStatus 常量）

        Returns:
            是否设置成功
        """
        channel = self._channels.get(channel_id)
        if not channel:
            return False

        old_status = channel.status
        channel.status = status
        logger.info(
            "渠道状态变更: %s (id=%d) %d → %d",
            channel.name, channel_id, old_status, status
        )
        return True

    def enable(self, channel_id: int) -> bool:
        """启用渠道"""
        return self.set_status(channel_id, ChannelStatus.ENABLED)

    def disable(self, channel_id: int) -> bool:
        """手动禁用渠道"""
        return self.set_status(channel_id, ChannelStatus.MANUAL_DISABLED)

    def auto_disable(self, channel_id: int) -> bool:
        """自动禁用渠道（断路器触发）"""
        channel = self._channels.get(channel_id)
        if not channel:
            return False
        channel.status = ChannelStatus.AUTO_DISABLED
        channel.auto_disabled_at = int(time.time())
        logger.warning("渠道 %s (id=%d) 已自动禁用", channel.name, channel_id)
        return True

    def load_from_config(self, channels_config: list[dict]) -> int:
        """
        从 YAML 配置加载渠道

        Args:
            channels_config: 渠道配置列表

        Returns:
            成功加载的渠道数量
        """
        count = 0
        for ch_cfg in channels_config:
            try:
                self.create(
                    name=ch_cfg.get("name", f"channel-{ch_cfg.get('id', count + 1)}"),
                    channel_type=ch_cfg.get("type", ChannelType.CUSTOM),
                    key=ch_cfg.get("api_keys", [""])[0] if ch_cfg.get("api_keys") else "",
                    base_url=ch_cfg.get("base_url", ""),
                    models=ch_cfg.get("models", []),
                    priority=ch_cfg.get("priority", 0),
                    weight=ch_cfg.get("weight", 0),
                    group=ch_cfg.get("group", "default"),
                    config=ch_cfg.get("config", {}),
                )
                count += 1
            except Exception as e:
                logger.error("加载渠道配置失败: %s", e)

        logger.info("已从配置加载 %d 个渠道", count)
        return count

    def warm_cache(self) -> dict[str, int]:
        """
        缓存预热 — 统计各分组的渠道数量

        Returns:
            分组名称 → 渠道数量的映射
        """
        stats: dict[str, int] = {}
        for channel in self._channels.values():
            group = channel.group
            stats[group] = stats.get(group, 0) + 1

        logger.info("缓存预热完成: %s", stats)
        return stats
