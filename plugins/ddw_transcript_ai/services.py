from __future__ import annotations

"""DDW 转写与结构化插件业务逻辑层。

本插件为**聚合 AI 能力插件**，全部能力通过 :class:`EmbeddedLLM` 调用 DDW 内置
LLM Gateway 完成。**不创建 ORM 模型，无任何数据库持久化。**

服务：
- :class:`TranscriptService` —— 暴露 4 个核心能力：
  - :meth:`transcribe` — 录音转写（模拟 ASR）
  - :meth:`summarize` — 文本摘要
  - :meth:`extract_todos` — 待办提取
  - :meth:`extract_entities` — 关键实体抽取

设计要点：
- LLM 调用统一通过 ``self.llm.chat(prompt, system=...)``，传入中文系统 prompt
  引导 LLM 输出期望的 JSON 结构
- 对 LLM 返回的字符串做宽松解析：先尝试 ``json.loads``，失败再用
  ``ast.literal_eval`` 兜底，再失败则按行/标点启发式拆分
- 所有解析都要 fallback：echo backend 在无真实模型时也能产生合理响应
"""

import ast
import json
import logging
import re
from typing import Any, Optional

from plugins.embedded_llm.engine import EmbeddedLLM

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 解析辅助：把 LLM 字符串响应解析为结构化数据
# ---------------------------------------------------------------------------


# JSON 代码块提取：优先匹配 ```json ... ``` / ``` ... ```，其次裸 JSON
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]+?)\s*```", re.IGNORECASE)
# 顶层 JSON 对象/数组（从 { 或 [ 开始，到对应闭合）
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]+\}", re.MULTILINE)
_JSON_ARRAY_RE = re.compile(r"\[[\s\S]+\]", re.MULTILINE)


def _extract_json_payload(text: str) -> Optional[str]:
    """从 LLM 输出里抽出最可能的 JSON 字符串（对象或数组）。"""
    if not text:
        return None
    # 1) markdown 代码块
    m = _JSON_BLOCK_RE.search(text)
    if m:
        return m.group(1).strip()
    # 2) 裸 JSON 对象
    m = _JSON_OBJECT_RE.search(text)
    if m:
        return m.group(0)
    # 3) 裸 JSON 数组
    m = _JSON_ARRAY_RE.search(text)
    if m:
        return m.group(0)
    return None


def _safe_parse_json(text: str) -> Any | None:
    """宽松解析 LLM 字符串：尝试 json -> ast -> None。"""
    payload = _extract_json_payload(text)
    if not payload:
        return None
    # 1) 标准 json
    try:
        return json.loads(payload)
    except (ValueError, TypeError):
        pass
    # 2) 兜底 ast.literal_eval（支持 Python 字面量）
    try:
        return ast.literal_eval(payload)
    except (ValueError, SyntaxError):
        pass
    return None


def _coerce_str_list(value: Any) -> list[str]:
    """把 LLM 输出规范化为 ``List[str]``。"""
    if value is None:
        return []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str):
                s = item.strip()
                if s:
                    out.append(s)
            elif isinstance(item, (int, float)):
                out.append(str(item))
            elif isinstance(item, dict):
                # 实体常见形态：{"name": "华为", "type": "company"} —— 取 name/value/text
                s = item.get("name") or item.get("value") or item.get("text")
                if isinstance(s, str) and s.strip():
                    out.append(s.strip())
        return out
    if isinstance(value, str):
        # 单字符串也接受，按行拆分
        return [line.strip() for line in value.splitlines() if line.strip()]
    return []


def _split_lines_fallback(text: str, min_len: int = 2) -> list[str]:
    """最终兜底：按行/编号/分号拆出非空条目。"""
    if not text:
        return []
    # 去掉 markdown 装饰
    cleaned = re.sub(r"^[\-\*•·]\s*", "", text, flags=re.MULTILINE)
    cleaned = re.sub(r"^\d+[.\)、]\s*", "", cleaned, flags=re.MULTILINE)
    out: list[str] = []
    for line in cleaned.splitlines():
        s = line.strip()
        if len(s) >= min_len:
            out.append(s)
    return out


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

# 转写：让 LLM 输出"基于 file_url 的模拟转写文本"
_TRANSCRIBE_SYSTEM = (
    "你是一名专业的 ASR（语音识别）转写助手。"
    "请根据用户给出的 file_url 推断场景（中文销售沟通/电话录音/会议等），"
    "输出一段合理的模拟转写文本（中文，2-4 句，自然口语）。"
    "只输出转写文本本身，不要任何解释、标签、markdown 代码块。"
)

# 摘要
_SUMMARIZE_SYSTEM = (
    "你是一名销售场景文本摘要助手。"
    "请基于用户给定的文本，输出一段简洁的中文摘要。"
    "要求：保留关键事实（人名/金额/时间/动作），不臆造内容。"
    "只输出摘要文本本身，不要任何解释、标签、markdown 代码块。"
)

# 待办提取 —— 明确要求 JSON 数组
_TODOS_SYSTEM = (
    "你是一名销售沟通待办提取助手。"
    "请从用户给定的中文文本中，识别所有可执行的下一步行动（待办事项）。"
    "严格按以下 JSON 数组格式输出（不要任何其他文字、不要 markdown 代码块）：\n"
    '["事项1", "事项2", "事项3"]\n'
    "如果没有可执行事项，返回空数组 []。"
    "每条事项要简洁、可执行（动词开头）。"
)

# 实体抽取 —— 明确要求 JSON 对象
_ENTITIES_SYSTEM = (
    "你是一名销售沟通关键信息抽取助手。"
    "请从用户给定的中文文本中抽取四类关键实体：公司/机构、人名、金额、日期。"
    "严格按以下 JSON 对象格式输出（不要任何其他文字、不要 markdown 代码块）：\n"
    '{"companies": [], "people": [], "amounts": [], "dates": []}\n'
    "规则：\n"
    "- companies: 公司或机构名称（如'华为技术有限公司'）\n"
    "- people: 人名（如'张三'）\n"
    "- amounts: 金额，保留原始写法（如'30万'、'￥5000'、'15000元'）\n"
    "- dates: 日期/时间，保留原始写法（如'2026-08-15'、'下周三'、'Q4'）\n"
    "未出现某类时返回空数组。"
)


# ---------------------------------------------------------------------------
# 业务服务
# ---------------------------------------------------------------------------


class TranscriptService:
    """转写与结构化业务服务。

    - 通过 :class:`EmbeddedLLM` 调用 DDW LLM Gateway
    - 不持久化任何数据：每次调用都是独立的请求-响应
    - 所有解析方法都对 echo backend / 真实 LLM 都能产出合理结果
    """

    def __init__(self, llm: EmbeddedLLM) -> None:
        self.llm = llm

    # ------------------------------------------------------------------ #
    # 工具
    # ------------------------------------------------------------------ #

    def _backend_name(self) -> str:
        return type(self.llm._backend).__name__

    def _model_name(self) -> str:
        return getattr(self.llm, "_model_name", "echo-model")

    # ------------------------------------------------------------------ #
    # 1) 转写
    # ------------------------------------------------------------------ #

    async def transcribe(
        self, file_url: str, language: str = "zh-CN"
    ) -> dict[str, Any]:
        """模拟 ASR 转写。

        - Echo backend 也能产出占位转写（不抛错）
        - 真实 LLM 应返回该 file_url 对应录音的转写文本
        """
        prompt = (
            f"请转写以下录音文件：\n"
            f"file_url: {file_url}\n"
            f"language: {language}\n"
            f"要求：根据 URL 推断上下文，给出一段真实感的中文转写文本。"
        )
        raw = await self.llm.chat(prompt, system=_TRANSCRIBE_SYSTEM)

        # echo backend: "[echo] kb=... prompt=..." —— 这种情况生成占位转写
        if raw.startswith("[echo]") or not raw.strip():
            transcript = self._placeholder_transcript(file_url, language)
        else:
            transcript = raw.strip()

        return {
            "file_url": file_url,
            "language": language,
            "transcript": transcript,
            "transcript_length": len(transcript),
            "backend": self._backend_name(),
            "model": self._model_name(),
        }

    @staticmethod
    def _placeholder_transcript(file_url: str, language: str) -> str:
        """Echo backend 时的占位转写（不依赖 LLM，行为可预测）。"""
        # 从 URL 抽出一段作为"标识"
        tail = file_url.rsplit("/", 1)[-1].split("?")[0] or "audio"
        if language.startswith("zh"):
            return (
                f"[模拟转写-{tail}] 客户经理您好，"
                f"关于您提到的需求我们这边已经初步评估，"
                f"下周安排一次技术交流对接预算和实施周期。"
            )
        return (
            f"[mock-transcript-{tail}] Hello, this is a simulated transcript. "
            f"We have reviewed your requirements and will follow up next week."
        )

    # ------------------------------------------------------------------ #
    # 2) 摘要
    # ------------------------------------------------------------------ #

    async def summarize(self, text: str, max_length: int = 200) -> dict[str, Any]:
        """生成文本摘要。

        - Echo backend: 截取原文前 max_length 字符
        - 真实 LLM: 应返回简洁摘要（不超过 max_length 字符）
        """
        prompt = (
            f"请将以下文本压缩为不超过 {max_length} 字的中文摘要：\n\n"
            f"```\n{text}\n```"
        )
        raw = await self.llm.chat(prompt, system=_SUMMARIZE_SYSTEM)

        if raw.startswith("[echo]") or not raw.strip():
            # echo 模式：拿原文的前 max_length 字符作为摘要
            summary = text.strip().replace("\n", " ")
            if len(summary) > max_length:
                summary = summary[: max(1, max_length - 1)].rstrip() + "…"
        else:
            summary = raw.strip()
            # 兜底：超过 max_length 时强制截断（防御 LLM 不遵守）
            if len(summary) > max_length * 2:  # 给 2x 容忍度
                summary = summary[: max(1, max_length - 1)].rstrip() + "…"

        original_length = len(text)
        summary_length = len(summary)
        ratio = (summary_length / original_length) if original_length > 0 else 0.0

        return {
            "summary": summary,
            "original_length": original_length,
            "summary_length": summary_length,
            "compression_ratio": round(ratio, 4),
            "backend": self._backend_name(),
            "model": self._model_name(),
        }

    # ------------------------------------------------------------------ #
    # 3) 待办提取
    # ------------------------------------------------------------------ #

    async def extract_todos(self, text: str) -> dict[str, Any]:
        """从文本中提取待办事项。"""
        prompt = (
            "请从以下中文文本中提取所有可执行的待办事项：\n\n"
            f"```\n{text}\n```"
        )
        raw = await self.llm.chat(prompt, system=_TODOS_SYSTEM)

        todos: list[str] = []
        if not raw.startswith("[echo]"):
            # 尝试 JSON 解析；解析成功（即使结果为空）即采用，仅真解析失败才启发式兜底
            parsed = _safe_parse_json(raw)
            if parsed is not None:
                todos = _coerce_str_list(parsed)
            elif raw.strip():
                todos = _split_lines_fallback(raw)
        # echo / 解析失败时：todos 保持空列表（业务方按需解释）

        return {
            "todos": todos,
            "count": len(todos),
            "backend": self._backend_name(),
            "model": self._model_name(),
        }

    # ------------------------------------------------------------------ #
    # 4) 实体抽取
    # ------------------------------------------------------------------ #

    async def extract_entities(self, text: str) -> dict[str, Any]:
        """抽取 4 类关键实体。"""
        prompt = (
            "请从以下中文文本中抽取四类关键实体（公司/人名/金额/日期）：\n\n"
            f"```\n{text}\n```"
        )
        raw = await self.llm.chat(prompt, system=_ENTITIES_SYSTEM)

        result: dict[str, list[str]] = {
            "companies": [],
            "people": [],
            "amounts": [],
            "dates": [],
        }

        if not raw.startswith("[echo]"):
            parsed = _safe_parse_json(raw)
            if isinstance(parsed, dict):
                result["companies"] = _coerce_str_list(parsed.get("companies"))
                result["people"] = _coerce_str_list(parsed.get("people"))
                result["amounts"] = _coerce_str_list(parsed.get("amounts"))
                result["dates"] = _coerce_str_list(parsed.get("dates"))

        total = sum(len(v) for v in result.values())

        return {
            **result,
            "total_count": total,
            "backend": self._backend_name(),
            "model": self._model_name(),
        }


__all__ = [
    "TranscriptService",
    # 解析辅助也暴露给测试使用
    "_coerce_str_list",
    "_extract_json_payload",
    "_safe_parse_json",
    "_split_lines_fallback",
]
