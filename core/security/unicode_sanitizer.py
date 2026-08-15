"""DDW Unicode 注入防护（§2.1）

技术规范 v1.0 §2.1：所有用户输入必须经过 sanitize_unicode 处理。

实现：
1. NFKC 归一化
2. 剥离危险 Unicode 类别（Cf 控制格式 / Co 私有使用 / Cn 未分配）
3. 显式剥离已知危险码位（零宽空格、方向格式符、BOM）
4. 迭代上限保护（max 10 次）
"""
from __future__ import annotations

import unicodedata
from typing import Final

# 零宽字符 / 方向格式符 / BOM
_DANGEROUS_CODEPOINTS: Final[frozenset[int]] = frozenset({
    0x200B,  # ZERO WIDTH SPACE
    0x200C,  # ZERO WIDTH NON-JOINER
    0x200D,  # ZERO WIDTH JOINER
    0x2060,  # WORD JOINER
    0xFEFF,  # ZERO WIDTH NO-BREAK SPACE (BOM)
    # BiDi 控制字符 (Trojan Source 攻击)
    0x202A, 0x202B, 0x202C, 0x202D, 0x202E,  # LRE/RLE/PDF/LRO/RLO
    0x2066, 0x2067, 0x2068, 0x2069,  # LRI/RLI/FSI/PDI
})

# 危险 Unicode 类别：Cf(控制格式) / Co(私有使用) / Cn(未分配)
_DANGEROUS_CATEGORIES: Final[frozenset[str]] = frozenset({"Cf", "Co", "Cn"})

# 最大迭代次数（防止攻击者构造无限归一化链）
_MAX_ITERATIONS: Final[int] = 10


def sanitize_unicode(text: str, max_length: int = 1_000_000) -> str:
    """清洗用户输入中的 Unicode 攻击字符。

    Args:
        text: 原始输入字符串
        max_length: 最大允许长度（默认 1MB）

    Returns:
        清洗后的安全字符串
    """
    if not isinstance(text, str):
        raise TypeError(f"sanitize_unicode 期望 str，得到 {type(text).__name__}")
    if len(text) > max_length:
        raise ValueError(f"输入长度 {len(text)} 超过最大允许 {max_length}")

    # 1. 显式剥离已知危险码位
    text = "".join(ch for ch in text if ord(ch) not in _DANGEROUS_CODEPOINTS)

    # 2. 迭代 NFKC 归一化（最多 10 次，防无限归一化）
    for _ in range(_MAX_ITERATIONS):
        normalized = unicodedata.normalize("NFKC", text)
        if normalized == text:
            break
        text = normalized
    else:
        # 达到最大迭代仍未稳定 → 拒绝
        raise ValueError("Unicode 归一化未在 10 次内稳定，可能被攻击")

    # 3. 剥离剩余危险类别
    text = "".join(
        ch for ch in text
        if unicodedata.category(ch) not in _DANGEROUS_CATEGORIES
    )

    return text


def is_safe_unicode(text: str) -> bool:
    """检查文本是否安全（不需要修改）。"""
    try:
        return sanitize_unicode(text) == text
    except (ValueError, TypeError):
        return False
