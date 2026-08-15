"""
YAML 渠道配置加载器

映射源: One API model/channel.go + model/channel_cache.go
核心职责:
1. 从 channels.yaml 加载渠道配置
2. 支持环境变量替换（${VAR_NAME}）
3. 支持运行时热更新
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# 环境变量替换正则
_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


def _replace_env_vars(value: str) -> str:
    """
    替换字符串中的环境变量占位符

    支持格式: ${VAR_NAME}
    如果环境变量不存在，保留原始占位符

    Args:
        value: 包含占位符的字符串

    Returns:
        替换后的字符串
    """
    def _replacer(match: re.Match) -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, match.group(0))

    return _ENV_VAR_PATTERN.sub(_replacer, value)


def _process_value(value: Any) -> Any:
    """递归处理配置值，替换环境变量"""
    if isinstance(value, str):
        return _replace_env_vars(value)
    elif isinstance(value, dict):
        return {k: _process_value(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_process_value(item) for item in value]
    return value


class ConfigLoader:
    """
    YAML 渠道配置加载器

    映射: One API model/channel.go + model/channel_cache.go

    功能:
    1. 从 YAML 文件加载渠道配置
    2. 支持环境变量替换（${VAR_NAME}）
    3. 支持运行时热更新
    4. 配置缓存
    """

    def __init__(self, config_path: str | Path | None = None):
        """
        初始化配置加载器

        Args:
            config_path: 配置文件路径，默认为 config/channels.yaml
        """
        if config_path is None:
            config_path = Path(__file__).parent / "config" / "channels.yaml"
        self._config_path = Path(config_path)
        self._config: dict = {}
        self._last_mtime: float = 0.0

    def load(self) -> dict:
        """
        加载配置文件

        Returns:
            配置字典
        """
        if not self._config_path.exists():
            logger.warning("配置文件不存在: %s", self._config_path)
            return {"channels": []}

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                raw_config = yaml.safe_load(f) or {}

            # 环境变量替换
            self._config = _process_value(raw_config)
            self._last_mtime = self._config_path.stat().st_mtime

            channel_count = len(self._config.get("channels", []))
            logger.info(
                "渠道配置已加载: %s (%d 个渠道)",
                self._config_path, channel_count
            )
            return self._config

        except Exception as e:
            logger.error("加载配置文件失败: %s", e)
            return {"channels": []}

    def reload_if_changed(self) -> bool:
        """
        如果配置文件有变更，重新加载

        Returns:
            是否重新加载了配置
        """
        if not self._config_path.exists():
            return False

        current_mtime = self._config_path.stat().st_mtime
        if current_mtime > self._last_mtime:
            logger.info("检测到配置文件变更，重新加载")
            self.load()
            return True
        return False

    def get_channels_config(self) -> list[dict]:
        """获取渠道配置列表"""
        if not self._config:
            self.load()
        return self._config.get("channels", [])

    def get_config_value(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        if not self._config:
            self.load()
        return self._config.get(key, default)

    @property
    def config_path(self) -> Path:
        """配置文件路径"""
        return self._config_path


# 全局配置加载器单例
_config_loader: ConfigLoader | None = None


def get_config_loader(config_path: str | Path | None = None) -> ConfigLoader:
    """获取全局配置加载器"""
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader(config_path)
    return _config_loader
