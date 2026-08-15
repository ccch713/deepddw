"""DDW Token 三层控制（§2.2）

技术规范 v1.0 §2.2：LLM 调用前对工具结果施加三层限制。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenLimits:
    """三层 Token 限制配置。"""
    l1_single_result: int = 50_000    # L1 单条工具结果
    l1_preview_chars: int = 2_000     # 超限后仅传预览大小
    l2_aggregated: int = 200_000      # L2 单消息聚合
    l3_display: int = 50              # L3 显示截断（紧凑视图）

    def validate(self) -> None:
        if self.l1_single_result <= 0:
            raise ValueError("l1_single_result 必须 > 0")
        if self.l2_aggregated <= self.l1_single_result:
            raise ValueError("l2_aggregated 必须 > l1_single_result")
        if self.l3_display >= self.l1_single_result:
            raise ValueError("l3_display 必须 < l1_single_result")


DEFAULT_LIMITS = TokenLimits()


def truncate_l1(result: str, limits: TokenLimits = DEFAULT_LIMITS) -> str:
    """L1：单条工具结果截断。超限持久化到磁盘并返回预览。"""
    limits.validate()
    if len(result) <= limits.l1_single_result:
        return result
    return (
        f"[L1 TRUNCATED: 原始 {len(result)} 字符已超出 {limits.l1_single_result} 上限]\n"
        f"{result[:limits.l1_preview_chars]}\n"
        f"...[已截断]..."
    )


def truncate_l2_aggregated(parts: list[str], limits: TokenLimits = DEFAULT_LIMITS) -> list[str]:
    """L2：聚合多条工具结果到单消息，超限时替换最大块为预览。"""
    limits.validate()
    total = sum(len(p) for p in parts)
    if total <= limits.l2_aggregated:
        return parts

    # 找出最大的块
    max_idx = max(range(len(parts)), key=lambda i: len(parts[i]))
    parts[max_idx] = truncate_l1(parts[max_idx], limits)
    return parts


def compact_view(text: str, limits: TokenLimits = DEFAULT_LIMITS) -> str:
    """L3：紧凑视图摘要。"""
    limits.validate()
    if len(text) <= limits.l3_display:
        return text
    return text[:limits.l3_display] + "..."
