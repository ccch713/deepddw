"""
SQLAlchemy 数据模型 — 渠道管理

映射源: One API model/channel.go:Channel (L20-41)
包含: Channel 渠道表、ChannelGroup 渠道分组、RequestLog 请求日志
"""
from __future__ import annotations


# 降级基类：SDK 不可用时使用 DeclarativeBase
try:
    from core.database.base import Base  # type: ignore[import]
except ImportError:
    from sqlalchemy.orm import DeclarativeBase

    class Base(DeclarativeBase):  # type: ignore[no-redef]
        """降级基类（SDK 不可用时）"""
        pass


from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    Index,
    Integer,
    String,
    Text,
)


class Channel(Base):
    """
    渠道表 — 映射 One API model/channel.go:Channel (L20-41)

    状态码:
    - 0: Unknown（未知）
    - 1: Enabled（启用）
    - 2: ManualDisabled（手动禁用）
    - 3: AutoDisabled（自动禁用）
    """
    __tablename__ = "llm_gateway_channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(Integer, default=0, nullable=False)          # ChannelType 枚举值
    name = Column(String(255), index=True, nullable=False)
    key = Column(Text, nullable=False)                          # API 密钥（加密存储）
    status = Column(Integer, default=1, nullable=False)        # 0=Unknown 1=Enabled 2=ManualDisabled 3=AutoDisabled
    weight = Column(Integer, default=0, nullable=False)        # 负载均衡权重
    priority = Column(Integer, default=0, nullable=False)      # 优先级（越大越高）
    base_url = Column(String(255), default="", nullable=False)
    balance = Column(Float, default=0.0)                        # USD 余额（-1 = 无限额度）
    models = Column(Text, default="", nullable=False)           # 逗号分隔的模型列表
    model_mapping = Column(Text, default="", nullable=False)    # 模型名映射 JSON
    group = Column(String(32), default="default", nullable=False)
    used_quota = Column(Integer, default=0, nullable=False)
    response_time = Column(Integer, default=0)                  # 响应时间（毫秒）
    test_time = Column(Integer, default=0)                      # 最后测试时间戳
    config = Column(JSON, default=dict)                         # 渠道特定配置
    system_prompt = Column(Text, default="")
    created_time = Column(Integer, default=0)

    # ── 健康监控字段 ──
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    consecutive_failures = Column(Integer, default=0)
    last_success_at = Column(Integer, default=0)
    last_failure_at = Column(Integer, default=0)
    auto_disabled_at = Column(Integer, default=0)               # 自动禁用时间
    retest_interval = Column(Integer, default=300)              # 重测间隔（秒）

    __table_args__ = (
        Index("ix_channel_status_group", "status", "group"),
        Index("ix_channel_priority", "priority"),
    )

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "status": self.status,
            "weight": self.weight,
            "priority": self.priority,
            "base_url": self.base_url,
            "balance": self.balance,
            "models": self.models.split(",") if self.models else [],
            "model_mapping": self.model_mapping,
            "group": self.group,
            "used_quota": self.used_quota,
            "response_time": self.response_time,
            "config": self.config or {},
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "consecutive_failures": self.consecutive_failures,
            "last_success_at": self.last_success_at,
            "last_failure_at": self.last_failure_at,
            "auto_disabled_at": self.auto_disabled_at,
            "created_time": self.created_time,
        }

    def get_model_list(self) -> list[str]:
        """获取支持的模型列表"""
        if not self.models:
            return []
        return [m.strip() for m in self.models.split(",") if m.strip()]

    def supports_model(self, model: str) -> bool:
        """检查渠道是否支持指定模型"""
        if not self.models:
            return True  # 未指定模型列表 = 支持所有模型
        return model in self.get_model_list()


class ChannelGroup(Base):
    """
    渠道分组表

    用于按业务场景分组管理渠道，如:
    - default: 默认分组
    - premium: 高优先级分组
    - backup: 备用分组
    """
    __tablename__ = "llm_gateway_channel_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(32), unique=True, index=True, nullable=False)
    description = Column(Text, default="")
    priority = Column(Integer, default=0)                       # 分组优先级
    enabled = Column(Boolean, default=True)
    created_time = Column(Integer, default=0)

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "priority": self.priority,
            "enabled": self.enabled,
        }


class RequestLog(Base):
    """
    请求日志表

    记录每个 LLM 请求的详细信息，用于:
    - 费用统计
    - 性能监控
    - 故障排查
    - 渠道健康度计算
    """
    __tablename__ = "llm_gateway_request_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(Integer, index=True, nullable=False)
    model = Column(String(255), nullable=False)
    user_id = Column(Integer, index=True, default=0)
    status_code = Column(Integer, default=0)                    # HTTP 状态码
    success = Column(Boolean, default=True)
    error_message = Column(Text, default="")
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    quota_cost = Column(Float, default=0.0)                     # 实际费用（USD）
    response_time = Column(Integer, default=0)                  # 响应时间（毫秒）
    is_stream = Column(Boolean, default=False)
    created_time = Column(Integer, default=0)

    __table_args__ = (
        Index("ix_request_log_model_time", "model", "created_time"),
        Index("ix_request_log_channel_time", "channel_id", "created_time"),
    )

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "id": self.id,
            "channel_id": self.channel_id,
            "model": self.model,
            "user_id": self.user_id,
            "status_code": self.status_code,
            "success": self.success,
            "error_message": self.error_message,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "quota_cost": self.quota_cost,
            "response_time": self.response_time,
            "is_stream": self.is_stream,
            "created_time": self.created_time,
        }
