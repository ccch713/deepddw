"""问渠学科包配置 — 全部从环境变量读取。"""
from __future__ import annotations

import os

# 钱包服务地址
WALLET_BASE: str = os.getenv(
    "DDW_WENQU_TUTOR_WALLET_BASE", "http://127.0.0.1:8500"
)

# DDW LLM Gateway
LLM_GATEWAY: str = os.getenv(
    "DDW_WENQU_TUTOR_LLM_GATEWAY", "http://127.0.0.1:8500"
)

# 对话主模型
MODEL: str = os.getenv(
    "DDW_WENQU_TUTOR_MODEL", "deepseek-v4-flash"
)

# 轻量模型（摘要/复盘）
FAST_MODEL: str = os.getenv(
    "DDW_WENQU_TUTOR_FAST_MODEL", "deepseek-v4-flash"
)

# 教材根目录
TEXTBOOK_ROOT: str = os.getenv(
    "DDW_WENQU_TUTOR_TEXTBOOK_ROOT", "/opt/wenqu/textbooks"
)

# 问渠独立 PG 数据库
DB_URL: str = os.getenv(
    "DDW_WENQU_TUTOR_DB_URL",
    "postgresql+asyncpg://localhost:5432/wenqu",
)

# 单课上限（分钟）
MAX_SESSION_MINUTES: int = int(
    os.getenv("DDW_WENQU_TUTOR_MAX_SESSION_MINUTES", "45")
)

# 活跃计时防挂机阈值（秒）
ACTIVE_TIMEOUT_SECONDS: int = 90

# ── M0-5 用量计费费率（用户拍板 2026-08-14）──────────────────
# 推理 token：DeepSeek 涨价后单价 × 4
#   deepseek-chat 涨价后：输入 ¥0.002/千（0.2 分/千）、输出 ¥0.008/千（0.8 分/千）
#   ×4 → 输入 800 分/百万、输出 3200 分/百万（单位：分/百万 token，避免浮点）
TOKEN_PRICE_IN_CENTS_PER_MILLION: int = int(
    os.getenv("DDW_WENQU_TUTOR_TOKEN_PRICE_IN", "800")
)
TOKEN_PRICE_OUT_CENTS_PER_MILLION: int = int(
    os.getenv("DDW_WENQU_TUTOR_TOKEN_PRICE_OUT", "3200")
)

# OCR / TTS：MiniMax 定价 × 3（OCR 管线 M0-7 激活后生效，先占位）
OCR_PRICE_CENTS_PER_PAGE: int = int(
    os.getenv("DDW_WENQU_TUTOR_OCR_PRICE", "20")
)  # 0.2 元/张
TTS_PRICE_CENTS_PER_1K_CHAR: int = int(
    os.getenv("DDW_WENQU_TUTOR_TTS_PRICE", "15")
)  # 0.15 元/千字

# 单会话 45 分钟用量封顶（25 元 → 2500 分，用户拍板）
BILLING_CAP_CENTS: int = int(
    os.getenv("DDW_WENQU_TUTOR_BILLING_CAP", "2500")
)

# 学习计费单价（分/活跃分钟）—— v0.1 旧费率，M0-5 起弃用（保留兼容）
RATE_STUDY_CENTS_PER_MINUTE: int = 1200  # deprecated

__all__ = [
    "ACTIVE_TIMEOUT_SECONDS",
    "BILLING_CAP_CENTS",
    "DB_URL",
    "FAST_MODEL",
    "LLM_GATEWAY",
    "MAX_SESSION_MINUTES",
    "MODEL",
    "OCR_PRICE_CENTS_PER_PAGE",
    "RATE_STUDY_CENTS_PER_MINUTE",
    "TEXTBOOK_ROOT",
    "TOKEN_PRICE_IN_CENTS_PER_MILLION",
    "TOKEN_PRICE_OUT_CENTS_PER_MILLION",
    "TTS_PRICE_CENTS_PER_1K_CHAR",
    "WALLET_BASE",
]
