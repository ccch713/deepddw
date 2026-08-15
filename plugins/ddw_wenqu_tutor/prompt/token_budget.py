"""CJK=1/非CJK=0.25 估算 + 截断。"""
from __future__ import annotations

import re

# CJK 字符正则（基本CJK + 扩展A + 兼容 + 扩展B）
CJK_RE = re.compile(
    r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]"
)


def estimate_tokens(text: str) -> int:
    """估算 token 数：CJK=1，非CJK=0.25。"""
    cjk_count = len(CJK_RE.findall(text))
    non_cjk = len(text) - cjk_count
    return cjk_count + int(non_cjk * 0.25)


def truncate_to_budget(
    text: str, max_tokens: int
) -> str:
    """按 token 预算截断文本。"""
    if estimate_tokens(text) <= max_tokens:
        return text
    # 逐步截断
    for i in range(len(text), 0, -1):
        if estimate_tokens(text[:i]) <= max_tokens:
            return text[:i]
    return ""


__all__ = ["estimate_tokens", "truncate_to_budget"]
