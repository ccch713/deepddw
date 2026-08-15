"""拍照错题 OCR（2026-08-14 移植 wenquK12 + 多模态真实实现）。

用视觉模型（OpenAI 兼容 image_url 格式）识别试卷/错题图片，
输出结构化题目列表；确认后入库（新题进公共题库=众筹，错题进错题本）。

视觉模型配置（环境变量）：
- DDW_WENQU_VISION_MODEL：默认 MiniMax-VL-01（MiniMax 视觉）
- DDW_WENQU_VISION_BASE_URL：默认 https://api.minimaxi.com/v1
- 也可指向硅基流动（MiMo key）的 Qwen-VL 等
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

VISION_MODEL = os.getenv("DDW_WENQU_VISION_MODEL", "MiniMax-VL-01")
VISION_BASE_URL = os.getenv(
    "DDW_WENQU_VISION_BASE_URL", "https://api.minimaxi.com/v1"
)


@dataclass
class ExamPaperOCR:
    """OCR 识别结果。"""
    raw_text: str = ""
    questions: list = field(default_factory=list)
    total_questions: int = 0
    confidence: float = 0.0


def _vision_api_key() -> str:
    """视觉模型 API key（优先独立配置，回退 MiniMax key）。"""
    key = os.getenv("DDW_WENQU_VISION_API_KEY", "")
    if key:
        return key
    key = os.getenv("DDW_MINIMAX_API_KEY", "")
    if key:
        return key
    try:
        with open(os.path.expanduser("~/.ddw_env")) as f:
            for line in f:
                if "MINIMAX_API_KEY" in line:
                    return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return ""


def _build_prompt(subject: str) -> str:
    """构建试卷识别提示词（要求 JSON 输出）。"""
    from plugins.ddw_wenqu_tutor.prompt.subject_meta import SUBJECT_NAMES

    subject_name = SUBJECT_NAMES.get(subject, "学科")
    return f"""请仔细识别这张{subject_name}试卷/错题图片中的所有题目。

要求：
1. 识别图片中的所有题目（包括题目正文、选项、图示描述）
2. 按顺序编号
3. 每道题输出格式：
   题目{{编号}}：{{题干内容}}
   选项A：{{A选项}}
   （如果没有选项则省略）

请用以下JSON格式输出：
{{
  "questions": [
    {{
      "number": 1,
      "text": "完整题目正文",
      "options": ["A. 选项1", "B. 选项2", ...],
      "answer": "正确答案（如可识别）",
      "explanation": "解析（如可识别）"
    }}
  ],
  "total": 题目总数
}}

只输出JSON，不要其他文字。"""


async def recognize_exam_paper(
    image_bytes: bytes,
    subject: str = "physics",
) -> ExamPaperOCR:
    """识别试卷/错题图片中的题目（视觉模型多模态调用）。"""
    mime = "image/jpeg" if image_bytes[:2] == b"\xff\xd8" else "image/png"
    data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"

    api_key = _vision_api_key()
    if not api_key:
        logger.warning("vision api key 未配置，OCR 返回空")
        return ExamPaperOCR(confidence=0.0)

    payload = {
        "model": VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": _build_prompt(subject)},
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 2000,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{VISION_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
        raw = data["choices"][0]["message"]["content"]
    except Exception as e:  # noqa: BLE001
        logger.error("OCR vision call failed: %s", e)
        return ExamPaperOCR(confidence=0.0)

    # 解析 JSON 题目列表
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            questions = parsed.get("questions", [])
            return ExamPaperOCR(
                raw_text=raw,
                questions=questions,
                total_questions=parsed.get("total", len(questions)),
                confidence=0.8,
            )
        except json.JSONDecodeError:
            logger.error("OCR JSON parse failed")

    return ExamPaperOCR(raw_text=raw, confidence=0.3)


def questions_to_mistake_records(
    questions: list,
    subject: str,
) -> list:
    """识别题目 → 错题记录草稿（移植 wenquK12）。"""
    records = []
    for q in questions or []:
        text = (q.get("text") or "").strip()
        if not text:
            continue
        records.append({
            "subject": subject,
            "title": text[:50],
            "question_text": text,
            "options": q.get("options", []),
            "answer": q.get("answer", ""),
            "explanation": q.get("explanation", ""),
            "source": "ocr_upload",
        })
    return records


__all__ = [
    "ExamPaperOCR",
    "questions_to_mistake_records",
    "recognize_exam_paper",
]
