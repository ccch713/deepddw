"""DDW Talk A1 ASR - Whisper 转写核心.

调用 whisper-cli（whisper-cpp）转写音频文件，输出 JSON 结果。
对 CLI 不可用的环境提供 mock 模式（单元测试用）。
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import config

logger = logging.getLogger(__name__)


class TranscriptionError(RuntimeError):
    """whisper 转写失败时抛出的异常."""


@dataclass
class TranscriptionResult:
    job_id: str
    audio_path: str
    full_text: str
    segments: list[dict[str, Any]] = field(default_factory=list)
    language: str = "zh"
    duration_seconds: float = 0.0
    model: str = ""
    transcribed_at: str = ""
    output_path: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "audio_path": self.audio_path,
            "full_text": self.full_text,
            "segments": self.segments,
            "language": self.language,
            "duration_seconds": self.duration_seconds,
            "model": self.model,
            "transcribed_at": self.transcribed_at,
            "output_path": self.output_path,
        }


def _is_mock_mode(audio_path: str) -> bool:
    """判断是否走 mock 模式：环境变量 DDW_TALK_A1_MOCK=1 或音频路径不存在但属测试场景."""
    if os.getenv("DDW_TALK_A1_MOCK") == "1":
        return True
    # 兜底：模型目录不存在时强制 mock，避免 CI 跑挂
    return not (config.WHISPER_MODEL_DIR / config.WHISPER_MODEL).exists()


def _mock_transcribe(audio_path: str) -> TranscriptionResult:
    """测试/演示用的 mock 实现，生成符合规范的 JSON."""
    job_id = uuid.uuid4().hex[:8]
    base = Path(audio_path).stem
    return TranscriptionResult(
        job_id=job_id,
        audio_path=audio_path,
        full_text=f"[mock] {base} 的转写文本。患者主诉牙痛三天，夜间加重，冷热刺激痛。",
        segments=[
            {"start": 0.0, "end": 3.5, "text": "患者主诉牙痛三天"},
            {"start": 3.5, "end": 7.2, "text": "夜间加重，冷热刺激痛"},
            {"start": 7.2, "end": 10.0, "text": "检查左上6远中邻面深龋"},
        ],
        language="zh",
        duration_seconds=10.0,
        model=config.WHISPER_MODEL,
        transcribed_at=datetime.now(timezone.utc).isoformat(),
    )


def transcribe_audio(
    audio_path: str,
    output_dir: Optional[Path] = None,
    *,
    model: Optional[str] = None,
    language: str = "zh",
) -> TranscriptionResult:
    """调用 whisper-cli 转写一个音频文件.

    Parameters
    ----------
    audio_path : str
        音频文件绝对路径
    output_dir : Path, optional
        whisper 输出目录，默认使用 config.OUTPUT_DIR
    model : str, optional
        覆盖默认模型名
    language : str
        语言代码，默认 zh

    Returns
    -------
    TranscriptionResult
        转写结果（segments + full_text + metadata）
    """
    audio = Path(audio_path)
    if not audio.exists():
        raise FileNotFoundError(f"audio file not found: {audio_path}")

    out_dir = Path(output_dir) if output_dir else config.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if _is_mock_mode(audio_path):
        result = _mock_transcribe(audio_path)
        result.output_path = str(out_dir / f"{result.job_id}.json")
        _persist(result)
        return result

    model_name = model or config.WHISPER_MODEL
    model_path = config.WHISPER_MODEL_DIR / model_name
    if not model_path.exists():
        raise FileNotFoundError(f"whisper model not found: {model_path}")

    job_id = uuid.uuid4().hex[:8]
    cmd = [
        str(config.WHISPER_CLI),
        "--model", str(model_path),
        "--language", language,
        "--output-format", "json",
        "--output-dir", str(out_dir),
        str(audio),
    ]
    logger.info("whisper-cli job %s: %s", job_id, " ".join(cmd))
    try:
        completed = subprocess.run(
            cmd, capture_output=True, text=True, timeout=config.JOB_TIMEOUT_SECONDS, check=False
        )
    except subprocess.TimeoutExpired as e:
        raise TranscriptionError(f"whisper-cli timeout: {e}") from e
    if completed.returncode != 0:
        raise TranscriptionError(
            f"whisper-cli failed (rc={completed.returncode}): {completed.stderr[:500]}"
        )

    json_path = out_dir / f"{audio.stem}.json"
    if not json_path.exists():
        raise TranscriptionError(f"whisper output missing: {json_path}")
    try:
        with open(json_path, encoding="utf-8") as f:
            whisper_data = json.load(f)
    except json.JSONDecodeError as e:
        raise TranscriptionError(f"invalid whisper output json: {e}") from e

    segments = [
        {"start": float(s.get("start", 0.0)), "end": float(s.get("end", 0.0)), "text": s.get("text", "")}
        for s in whisper_data.get("segments", [])
    ]
    duration = float(whisper_data.get("duration", segments[-1]["end"] if segments else 0.0))
    result = TranscriptionResult(
        job_id=job_id,
        audio_path=str(audio),
        full_text=whisper_data.get("text", "").strip(),
        segments=segments,
        language=whisper_data.get("language", language),
        duration_seconds=duration,
        model=model_name,
        transcribed_at=datetime.now(timezone.utc).isoformat(),
    )
    result.output_path = str(out_dir / f"{job_id}.json")
    _persist(result)
    return result


def _persist(result: TranscriptionResult) -> None:
    """把结果写到 output 目录的 {job_id}.json."""
    if not result.output_path:
        result.output_path = str(config.OUTPUT_DIR / f"{result.job_id}.json")
    Path(result.output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(result.output_path, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
