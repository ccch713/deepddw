"""
倍率配置加载器 — 从 YAML 加载 569 个模型的倍率

对应 One API 源码映射:
- 倍率系统  → relay/billing/ratio/model.go
- group_ratio → relay/billing/ratio/group.go
- completion_ratio → relay/billing/ratio/completion.go

支持:
- 运行时热更新（文件修改后自动重载）
- 输入/输出倍率/分组倍率查询
- 深度思考模型特殊处理（DeepSeek Reasoner 等）
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

# ── 常量 ─────────────────────────────────────────────────────────
# 对应 One API relay/billing/ratio/constant.go
USD = 500          # $0.002 = 1 quota unit
MILLI_USD = 0.5    # 1.0 / 1000 * USD
RMB = 71.43        # USD / USD2RMB
USD2RMB = 7

# 深度思考模型的输出倍率覆盖（DDW独有）
# 对应 MiMo 分析报告 3.5 节
REASONING_OUTPUT_OVERRIDES: dict[str, float] = {
    "deepseek-reasoner": 2.19,    # DeepSeek Reasoner 输出倍率 / 输入倍率
    "deepseek-r1": 2.19,
}


class ModelRatioLoader:
    """
    模型倍率配置加载器

    从 YAML 文件加载所有模型的输入倍率、输出倍率和分组倍率。
    支持文件级热更新（通过 mtime 检测）。

    用法:
        loader = ModelRatioLoader("/path/to/model_ratios.yaml")
        ratio = loader.get_input_ratio("gpt-4o")       # 输入倍率
        comp = loader.get_completion_ratio("gpt-4o")    # 输出相对输入的倍数
        group = loader.get_group_ratio("default")        # 分组倍率
    """

    def __init__(self, yaml_path: str | Path) -> None:
        self._yaml_path = Path(yaml_path)
        self._data: dict[str, Any] = {}
        self._flat_ratios: dict[str, float] = {}      # model_name → input_ratio
        self._flat_completions: dict[str, float] = {}  # model_name → completion_ratio
        self._group_ratios: dict[str, float] = {}      # group_name → ratio
        self._last_mtime: float = 0.0
        self._constants: dict[str, float] = {}

        self._load()

    # ── 公开 API ──────────────────────────────────────────────────

    def get_input_ratio(self, model: str, channel_type: int = 0) -> float:
        """
        获取模型输入倍率

        对应 One API: billingratio.GetModelRatio(modelName, channelType)

        Args:
            model: 模型名称
            channel_type: 渠道类型（预留，当前未使用）

        Returns:
            输入倍率，未找到时返回 1.0
        """
        self._maybe_reload()
        return self._flat_ratios.get(model, 1.0)

    def get_completion_ratio(self, model: str, channel_type: int = 0) -> float:
        """
        获取模型输出倍率（相对于输入的倍数）

        对应 One API: billingratio.GetCompletionRatio(modelName, channelType)
        实际 quota = ceil((promptTokens + completionTokens * completionRatio) * modelRatio)

        Args:
            model: 模型名称
            channel_type: 渠道类型

        Returns:
            输出相对输入的倍数，默认 1.0
        """
        self._maybe_reload()

        # 深度思考模型特殊处理
        if model in REASONING_OUTPUT_OVERRIDES:
            return REASONING_OUTPUT_OVERRIDES[model]

        return self._flat_completions.get(model, 1.0)

    def get_group_ratio(self, group: str = "default") -> float:
        """
        获取分组倍率

        对应 One API: billingratio.GetGroupRatio(groupName)

        Args:
            group: 分组名称

        Returns:
            分组倍率
        """
        self._maybe_reload()
        return self._group_ratios.get(group, 1.0)

    def calculate_quota(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        channel_type: int = 0,
        group: str = "default",
    ) -> int:
        """
        计算单次请求的 quota 消耗

        对应 One API: relay/controller/helper.go:postConsumeQuota (L97-141)
        quota = ceil((promptTokens + completionTokens * completionRatio) * modelRatio * groupRatio)

        Args:
            model: 模型名称
            prompt_tokens: 输入 token 数
            completion_tokens: 输出 token 数
            channel_type: 渠道类型
            group: 用户分组

        Returns:
            quota 消耗量（整数）
        """
        import math

        model_ratio = self.get_input_ratio(model, channel_type)
        completion_ratio = self.get_completion_ratio(model, channel_type)
        group_ratio = self.get_group_ratio(group)

        quota = math.ceil(
            (float(prompt_tokens) + float(completion_tokens) * completion_ratio)
            * model_ratio
            * group_ratio
        )

        # 对应 helper.go L107-109: ratio != 0 时 quota <= 0 则设为 1
        if model_ratio != 0 and quota <= 0:
            quota = 1

        return quota

    def get_all_models(self) -> list[str]:
        """获取所有已配置的模型名称列表"""
        self._maybe_reload()
        return sorted(self._flat_ratios.keys())

    def get_model_count(self) -> int:
        """获取已配置模型总数"""
        self._maybe_reload()
        return len(self._flat_ratios)

    def reload(self) -> None:
        """强制重新加载配置"""
        self._load()

    # ── 内部方法 ──────────────────────────────────────────────────

    def _load(self) -> None:
        """加载并解析 YAML 配置文件"""
        if not self._yaml_path.exists():
            logger.warning("倍率配置文件不存在: %s", self._yaml_path)
            return

        try:
            with open(self._yaml_path, "r", encoding="utf-8") as f:
                self._data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            logger.error("倍率配置文件解析失败: %s", e)
            return

        self._last_mtime = self._yaml_path.stat().st_mtime

        # 解析常量
        self._constants = self._data.get("constants", {})

        # 解析分组倍率
        self._group_ratios = self._data.get("group_ratios", {"default": 1.0})

        # 解析模型倍率（扁平化）
        self._flat_ratios = {}
        self._flat_completions = {}

        for provider_name, models in self._data.items():
            if provider_name in ("constants", "group_ratios"):
                continue
            if not isinstance(models, dict):
                continue

            for model_name, value in models.items():
                # 值可能是数字或表达式字符串（如 "0.04 * USD"）
                ratio = self._parse_ratio_value(value)
                if ratio is not None:
                    self._flat_ratios[model_name] = ratio
                    # 默认 completion_ratio = 1.0
                    if model_name not in self._flat_completions:
                        self._flat_completions[model_name] = 1.0

        logger.info(
            "倍率配置已加载: %d 个模型, %d 个分组",
            len(self._flat_ratios),
            len(self._group_ratios),
        )

    def _parse_ratio_value(self, value: Any) -> Optional[float]:
        """
        解析倍率值，支持:
        - 纯数字: 2.5
        - 表达式字符串: "0.04 * USD", "0.0005 * RMB"
        """
        if isinstance(value, (int, float)):
            return float(value)

        if isinstance(value, str):
            # 替换常量
            expr = value
            for const_name, const_val in self._constants.items():
                expr = expr.replace(const_name, str(const_val))
            try:
                # 安全求值（仅允许数字和基本运算符）
                result = eval(expr, {"__builtins__": {}}, {})
                return float(result)
            except Exception:
                logger.warning("无法解析倍率表达式: %s", value)
                return None

        return None

    def _maybe_reload(self) -> None:
        """检测文件修改时间，自动热更新"""
        if not self._yaml_path.exists():
            return
        current_mtime = self._yaml_path.stat().st_mtime
        if current_mtime > self._last_mtime:
            logger.info("检测到倍率配置文件变更，重新加载")
            self._load()


# 全局单例（模块级别）
_loader_instance: Optional[ModelRatioLoader] = None


def get_ratio_loader(yaml_path: str | Path | None = None) -> ModelRatioLoader:
    """获取全局倍率加载器实例"""
    global _loader_instance
    if _loader_instance is None:
        if yaml_path is None:
            # 默认路径
            plugin_dir = Path(__file__).parent
            yaml_path = plugin_dir / "config" / "model_ratios.yaml"
        _loader_instance = ModelRatioLoader(yaml_path)
    return _loader_instance
