"""
渠道管理器测试

覆盖:
- CRUD 操作
- 状态管理
- 模型过滤
- 分组过滤
- 配置加载
"""
from __future__ import annotations

from ddw_llm_gateway.channel_manager import ChannelManager, ChannelStatus
from ddw_llm_gateway.channel_types import ChannelType


class TestChannelManager:
    """渠道管理器测试"""

    def setup_method(self):
        """每个测试方法前初始化"""
        self.cm = ChannelManager()

    def test_create_channel(self):
        """创建渠道"""
        channel = self.cm.create(
            name="test-channel",
            channel_type=ChannelType.MINIMAX,
            key="sk-test",
            base_url="https://api.minimax.chat",
            models=["MiniMax-Text-01"],
            priority=10,
            weight=100,
            group="default",
        )

        assert channel.id > 0
        assert channel.name == "test-channel"
        assert channel.type == ChannelType.MINIMAX
        assert channel.status == ChannelStatus.ENABLED
        assert channel.priority == 10
        assert channel.weight == 100

    def test_create_channel_default_base_url(self):
        """创建渠道时自动填充默认 base_url"""
        channel = self.cm.create(
            name="test-channel",
            channel_type=ChannelType.DEEPSEEK,
            key="sk-test",
        )

        assert channel.base_url == "https://api.deepseek.com"

    def test_get_channel(self):
        """获取渠道"""
        channel = self.cm.create(
            name="test-channel",
            channel_type=ChannelType.MINIMAX,
            key="sk-test",
        )

        found = self.cm.get(channel.id)
        assert found is not None
        assert found.name == "test-channel"

    def test_get_nonexistent_channel(self):
        """获取不存在的渠道"""
        found = self.cm.get(999)
        assert found is None

    def test_update_channel(self):
        """更新渠道"""
        channel = self.cm.create(
            name="test-channel",
            channel_type=ChannelType.MINIMAX,
            key="sk-test",
        )

        updated = self.cm.update(channel.id, name="updated-name", priority=20)
        assert updated is not None
        assert updated.name == "updated-name"
        assert updated.priority == 20

    def test_delete_channel(self):
        """删除渠道"""
        channel = self.cm.create(
            name="test-channel",
            channel_type=ChannelType.MINIMAX,
            key="sk-test",
        )

        success = self.cm.delete(channel.id)
        assert success is True
        assert self.cm.get(channel.id) is None

    def test_delete_nonexistent_channel(self):
        """删除不存在的渠道"""
        success = self.cm.delete(999)
        assert success is False

    def test_list_all(self):
        """列出所有渠道"""
        self.cm.create(name="ch1", channel_type=ChannelType.MINIMAX, key="k1")
        self.cm.create(name="ch2", channel_type=ChannelType.DEEPSEEK, key="k2")

        all_channels = self.cm.list_all()
        assert len(all_channels) == 2

    def test_list_enabled(self):
        """列出启用的渠道"""
        ch1 = self.cm.create(name="ch1", channel_type=ChannelType.MINIMAX, key="k1")
        ch2 = self.cm.create(name="ch2", channel_type=ChannelType.DEEPSEEK, key="k2")
        self.cm.disable(ch2.id)

        enabled = self.cm.list_enabled()
        assert len(enabled) == 1
        assert enabled[0].id == ch1.id

    def test_list_by_model(self):
        """按模型过滤渠道"""
        self.cm.create(
            name="ch1", channel_type=ChannelType.MINIMAX, key="k1",
            models=["MiniMax-Text-01", "gpt-4"],
        )
        self.cm.create(
            name="ch2", channel_type=ChannelType.DEEPSEEK, key="k2",
            models=["deepseek-chat"],
        )

        result = self.cm.list_by_model("gpt-4")
        assert len(result) == 1
        assert result[0].name == "ch1"

    def test_list_by_group(self):
        """按分组过滤渠道"""
        self.cm.create(name="ch1", channel_type=ChannelType.MINIMAX, key="k1", group="default")
        self.cm.create(name="ch2", channel_type=ChannelType.DEEPSEEK, key="k2", group="premium")

        result = self.cm.list_by_group("premium")
        assert len(result) == 1
        assert result[0].name == "ch2"

    def test_set_status(self):
        """设置渠道状态"""
        channel = self.cm.create(
            name="test-channel", channel_type=ChannelType.MINIMAX, key="sk-test",
        )

        success = self.cm.set_status(channel.id, ChannelStatus.MANUAL_DISABLED)
        assert success is True
        assert channel.status == ChannelStatus.MANUAL_DISABLED

    def test_auto_disable(self):
        """自动禁用渠道"""
        channel = self.cm.create(
            name="test-channel", channel_type=ChannelType.MINIMAX, key="sk-test",
        )

        success = self.cm.auto_disable(channel.id)
        assert success is True
        assert channel.status == ChannelStatus.AUTO_DISABLED
        assert channel.auto_disabled_at > 0

    def test_load_from_config(self):
        """从配置加载渠道"""
        config = [
            {
                "name": "minimax-primary",
                "type": ChannelType.MINIMAX,
                "api_keys": ["sk-test-1"],
                "base_url": "https://api.minimax.chat",
                "models": ["MiniMax-Text-01"],
                "priority": 10,
                "weight": 100,
                "group": "default",
            },
            {
                "name": "deepseek-v4",
                "type": ChannelType.DEEPSEEK,
                "api_keys": ["sk-test-2"],
                "models": ["deepseek-chat"],
                "priority": 5,
                "weight": 80,
            },
        ]

        count = self.cm.load_from_config(config)
        assert count == 2
        assert len(self.cm.list_all()) == 2

    def test_warm_cache(self):
        """缓存预热"""
        self.cm.create(name="ch1", channel_type=ChannelType.MINIMAX, key="k1", group="default")
        self.cm.create(name="ch2", channel_type=ChannelType.DEEPSEEK, key="k2", group="premium")

        stats = self.cm.warm_cache()
        assert stats["default"] == 1
        assert stats["premium"] == 1

    def test_channel_supports_model(self):
        """渠道模型支持检查"""
        channel = self.cm.create(
            name="ch1", channel_type=ChannelType.MINIMAX, key="k1",
            models=["gpt-4", "gpt-3.5-turbo"],
        )

        assert channel.supports_model("gpt-4") is True
        assert channel.supports_model("deepseek-chat") is False

    def test_channel_get_model_list(self):
        """获取渠道模型列表"""
        channel = self.cm.create(
            name="ch1", channel_type=ChannelType.MINIMAX, key="k1",
            models=["gpt-4", "gpt-3.5-turbo"],
        )

        models = channel.get_model_list()
        assert models == ["gpt-4", "gpt-3.5-turbo"]

    def test_channel_to_dict(self):
        """渠道序列化"""
        channel = self.cm.create(
            name="ch1", channel_type=ChannelType.MINIMAX, key="k1",
            models=["gpt-4"],
        )

        d = channel.to_dict()
        assert d["name"] == "ch1"
        assert d["type"] == ChannelType.MINIMAX
        assert d["models"] == ["gpt-4"]
