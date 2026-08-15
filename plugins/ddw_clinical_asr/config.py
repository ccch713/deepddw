"""DDW Clinical ASR - 配置管理."""
from __future__ import annotations

import os
from pathlib import Path

# LLM 优先级：MiniMax-M3 → DeepSeek → 知识库兜底
DEFAULT_MODEL = os.getenv("DDW_CLINICAL_DEFAULT_MODEL", "MiniMax-M3")
FALLBACK_MODELS = os.getenv("DDW_CLINICAL_FALLBACK_MODELS", "deepseek-chat").split(",")

# 部署配置（用于非 mock 模式下的 LLM endpoint）
DEPLOYMENT_CONFIG = Path(
    os.getenv(
        "DDW_DEPLOYMENT_CONFIG",
        str(Path.home() / "workspace" / "ddw-ai-hub" / "config" / "deployment.yaml"),
    )
)

# 路径
PLUGIN_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = PLUGIN_ROOT / "prompts"
DATA_DIR = PLUGIN_ROOT / "data"
DB_PATH = DATA_DIR / "clinical_asr.db"

# 抽取参数
EXTRACTION_TIMEOUT_SECONDS = int(os.getenv("DDW_CLINICAL_TIMEOUT", "30"))
MAX_TRANSCRIPT_CHARS = 8000
