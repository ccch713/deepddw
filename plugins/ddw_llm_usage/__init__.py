"""DDW LLM 用量统计与计费插件（用量中枢底座）。

模块名：ddw_llm_usage（下划线命名，DDW 插件规范）
提供：
    - LLM 调用记录的写入（幂等：同 id 重复提交忽略）
    - 按 model / plugin / user / day 的统计聚合
    - 可配置的单价表（PUT /prices/{model}）
    - 费用按 Decimal 精确计算，最终以「分（int）」存储
"""

from __future__ import annotations

VERSION = "0.1.0"
PLUGIN_NAME = "ddw_llm_usage"

__all__ = ["PLUGIN_NAME", "VERSION"]
