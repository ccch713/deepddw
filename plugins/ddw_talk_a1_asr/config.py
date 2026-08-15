"""DDW Talk A1 ASR - 配置管理.

从环境变量加载配置，提供默认值。所有路径相对于插件根目录解析。
"""
from __future__ import annotations

import os
from pathlib import Path

# Whisper 模型与 CLI
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "ggml-medium.bin")
WHISPER_MODEL_DIR = Path(
    os.getenv("WHISPER_MODEL_DIR", str(Path.home() / "models" / "whisper"))
)
WHISPER_CLI = os.getenv("WHISPER_CLI", "whisper-cli")

# 音频规格
AUDIO_SAMPLE_RATE = 16000  # whisper 要求 16kHz 单声道
AUDIO_CHANNELS = 1
ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".m4b", ".ogg", ".flac"}
MAX_AUDIO_BYTES = 200 * 1024 * 1024  # 200MB 上限

# 并发与超时
MAX_CONCURRENT_JOBS = 3
JOB_TIMEOUT_SECONDS = 300

# 路径（相对于插件目录）
PLUGIN_ROOT = Path(__file__).resolve().parent
QUEUE_DIR = PLUGIN_ROOT / "audio_queue"
OUTPUT_DIR = PLUGIN_ROOT / "output"
DATA_DIR = PLUGIN_ROOT / "data"
DB_PATH = DATA_DIR / "talk_a1_asr.db"

# 状态机
JOB_STATUSES = ("queued", "transcribing", "completed", "failed")
SESSION_TYPES = ("consultation", "follow_up", "emergency")

# 兜底：兜底常量，业务方可由 settings 覆盖
PROGRESS_TRANSIENT = 0.6  # 转写中时 GET 接口返回的 progress 兜底值
