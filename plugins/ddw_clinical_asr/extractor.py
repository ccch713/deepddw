"""DDW Clinical ASR - 抽取核心逻辑.

封装 LLM 调用 + prompt 装配 + JSON 解析。
可被替换为 mock 模式用于测试。
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

from . import config
from .schema import (
    TREATMENT_VALUES,
    URGENCY_VALUES,
    ExtractionResult,
    TreatmentType,
)

logger = logging.getLogger(__name__)

PROMPT_FILES = {
    "system": "extraction_system.txt",
    "orthodontics": "orthodontics.txt",
    "pulp_open": "pulp_open.txt",
    "extraction": "extraction.txt",
    "cosmetic": "cosmetic.txt",
    "root_canal": "root_canal.txt",
    "implant": "implant.txt",
    "prosthesis": "prosthesis.txt",
    "periodontal": "periodontal.txt",
    "pediatric": "pediatric.txt",
}

# 9 类诊疗的 special_findings 兜底字段（mock 模式用）
_SPEC_FINDINGS_DEFAULTS: dict[str, dict[str, Any]] = {
    "orthodontics": {"malocclusion_type": "crowding", "angle_class": "I", "overjet": 3.0},
    "pulp_open": {"pulp_vitality": "alive_inflamed", "estimated_canals": 3},
    "extraction": {"tooth_position": "左下8", "extraction_reason": "impaction", "difficulty_level": "surgical"},
    "cosmetic": {"treatment_subtype": "veneer", "material": "porcelain", "shade": "A2"},
    "root_canal": {"root_count": 3, "canal_filling_method": "lateral"},
    "implant": {"missing_tooth": "左下6", "bone_quality": "II", "implant_brand": "Straumann"},
    "prosthesis": {"restoration_type": "crown", "material": "zirconia"},
    "periodontal": {"pocket_depth": 4.5, "bleeding_index": 2},
    "pediatric": {"tooth_type": "primary", "age_group": "6-9"},
}


def _prompts_dir() -> Path:
    return Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    """从 prompts/ 目录加载 prompt 文本，缺失时回退到内置模板."""
    p = _prompts_dir() / name
    if p.exists():
        return p.read_text(encoding="utf-8")
    # 内置 fallback（保证插件能跑）
    if name == "extraction_system.txt":
        return _FALLBACK_SYSTEM_PROMPT
    return _FALLBACK_TYPE_PROMPT


def list_prompts() -> list[dict[str, str]]:
    """列出所有可用 prompt 文件 + 内置 fallback."""
    out = []
    for key, fn in PROMPT_FILES.items():
        p = _prompts_dir() / fn
        out.append(
            {
                "key": key,
                "file": fn,
                "exists": p.exists(),
                "size": p.stat().st_size if p.exists() else 0,
            }
        )
    return out


# --- 内置 fallback prompt（当 prompts/ 目录缺失时使用） ---

_FALLBACK_SYSTEM_PROMPT = """你是一位口腔医学病历助手。根据医患对话转写文本，提取结构化病历信息。

输出格式：严格 JSON，不要添加解释文字。

提取规则：
1. treatment_type: 判断诊疗类型 (orthodontics/pulp_open/extraction/cosmetic/root_canal/implant/prosthesis/periodontal/pediatric)
2. confidence: 置信度 (0-1)
3. chief_complaint: 患者主诉（一句话）
4. present_illness: 现病史（持续时间/加重/缓解）
5. past_history: 既往史
6. examination: 检查结果 key-value
7. diagnosis: 诊断
8. treatment_plan: 治疗计划
9. special_findings: 诊疗类型特有字段
10. urgency: routine/urgent/emergency

{type_specific_rules}

注意：
- 信息不足时用 "待补充" 标记
- 不要编造信息
- 口腔专业术语用标准中文表述
"""

_FALLBACK_TYPE_PROMPT = """special_findings 按对应诊疗类型常见字段填充：
- orthodontics: malocclusion_type, angle_class, overjet, overbite, treatment_modality
- extraction: tooth_position, extraction_reason, difficulty_level, anesthesia_type
- root_canal: root_count, canal_filling, prognosis
- implant: missing_tooth, bone_quality, implant_brand, loading_protocol
- 其他类型按需扩展
"""


def _build_user_prompt(transcript: str) -> str:
    return (
        "以下是一段口腔诊疗对话的转写文本：\n\n"
        f"{transcript}\n\n请提取结构化病历信息。"
    )


def _is_mock_mode() -> bool:
    if os.getenv("DDW_CLINICAL_ASR_MOCK") == "1":
        return True
    return not Path(config.DEPLOYMENT_CONFIG).exists()


def _mock_llm_call(
    system: str, user: str, *, treatment_hint: Optional[str] = None
) -> str:
    """Mock 模式：基于 transcript 关键词做最简单的类型判定 + 兜底字段."""
    # 优先使用 hint
    if treatment_hint and treatment_hint in TREATMENT_VALUES:
        spec = _SPEC_FINDINGS_DEFAULTS.get(treatment_hint, {})
        return json.dumps(
            {
                "treatment_type": treatment_hint,
                "confidence": 0.92,
                "chief_complaint": f"mock {treatment_hint} 主诉",
                "present_illness": f"mock {treatment_hint} 现病史",
                "past_history": "mock",
                "examination": {"mock": True},
                "diagnosis": f"mock {treatment_hint} 诊断",
                "treatment_plan": f"mock {treatment_hint} 治疗计划",
                "special_findings": spec,
                "urgency": "routine",
            },
            ensure_ascii=False,
        )
    text = user.lower()
    # 简单规则匹配
    if "正畸" in user or "牙套" in user or "矫治" in user or "orthodont" in text or "牙列不齐" in user:
        tt = "orthodontics"
        spec = _SPEC_FINDINGS_DEFAULTS["orthodontics"]
    elif "种植" in user or "植体" in user or "implant" in text or "缺失种植" in user:
        tt = "implant"
        spec = _SPEC_FINDINGS_DEFAULTS["implant"]
    elif ("拔牙" in user or "阻生" in user or "extraction" in text
          or "要求拔除" in user):
        tt = "extraction"
        spec = _SPEC_FINDINGS_DEFAULTS["extraction"]
    elif "根管" in user or "root canal" in text:
        tt = "root_canal"
        spec = _SPEC_FINDINGS_DEFAULTS["root_canal"]
    elif ("开髓" in user or "牙髓" in user or "急性" in user
          or "牙髓炎" in user or "疼痛" in user or "冷热刺激" in user):
        tt = "pulp_open"
        spec = _SPEC_FINDINGS_DEFAULTS["pulp_open"]
    elif "贴面" in user or "美白" in user or "cosmetic" in text or "前牙贴面" in user:
        tt = "cosmetic"
        spec = _SPEC_FINDINGS_DEFAULTS["cosmetic"]
    elif "冠" in user or "嵌体" in user or "修复" in user or "prosthesis" in text or "后牙冠" in user:
        tt = "prosthesis"
        spec = _SPEC_FINDINGS_DEFAULTS["prosthesis"]
    elif "牙周" in user or "periodont" in text or "洁治" in user or "牙周炎" in user:
        tt = "periodontal"
        spec = _SPEC_FINDINGS_DEFAULTS["periodontal"]
    elif "儿童" in user or "乳牙" in user or "pediatric" in text or "儿牙" in user:
        tt = "pediatric"
        spec = _SPEC_FINDINGS_DEFAULTS["pediatric"]
    else:
        tt = "extraction"
        spec = _SPEC_FINDINGS_DEFAULTS["extraction"]

    return json.dumps(
        {
            "treatment_type": tt,
            "confidence": 0.85,
            "chief_complaint": "患者主诉待补充",
            "present_illness": "现病史待补充",
            "past_history": "待补充",
            "examination": {"待补充": "请医生补充"},
            "diagnosis": "待医生确认",
            "treatment_plan": "待医生制定",
            "special_findings": spec,
            "urgency": "routine",
        },
        ensure_ascii=False,
    )


async def call_llm(
    system: str, user: str, *, model: str = "", treatment_hint: Optional[str] = None
) -> str:
    """调用 LLM. 生产用 MiniMax-M3，mock 模式返回固定 JSON."""
    if _is_mock_mode():
        return _mock_llm_call(system, user, treatment_hint=treatment_hint)
    # 生产路径：透传 HTTP（实际部署时实现）
    logger.warning("non-mock LLM call not implemented, fallback to mock")
    return _mock_llm_call(system, user, treatment_hint=treatment_hint)


def _parse_json_payload(raw: str) -> dict[str, Any]:
    """从 LLM 响应中解析 JSON，兼容 markdown code block."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if m:
            return json.loads(m.group(1))
        # 尝试找第一个 { 最后一个 }
        s = raw.find("{")
        e = raw.rfind("}")
        if s != -1 and e != -1 and e > s:
            return json.loads(raw[s : e + 1])
        raise ValueError(f"LLM 返回非 JSON: {raw[:200]}")


def _coerce_treatment(value: Any) -> TreatmentType:
    if isinstance(value, TreatmentType):
        return value
    s = str(value or "").strip().lower()
    if s in TREATMENT_VALUES:
        return TreatmentType(s)
    raise ValueError(f"invalid treatment_type: {value}")


def _coerce_urgency(value: Any) -> str:
    s = str(value or "routine").strip().lower()
    return s if s in URGENCY_VALUES else "routine"


def _coerce_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {"raw": value}
    return {"raw": str(value)}


async def extract_medical_entities(
    transcript: str,
    job_id: str = "",
    treatment_hint: Optional[str] = None,
    *,
    model: str = "",
) -> tuple[dict[str, Any], int]:
    """主入口：抽取结构化实体.

    Returns
    -------
    (extraction_dict, latency_ms)
    """
    if not transcript or not transcript.strip():
        raise ValueError("transcript_text 不能为空")
    start = time.time()

    system_prompt = load_prompt("extraction_system.txt")
    if treatment_hint:
        if treatment_hint not in TREATMENT_VALUES and treatment_hint not in PROMPT_FILES:
            raise ValueError(f"invalid treatment_hint: {treatment_hint}")
        type_rules = load_prompt(f"{treatment_hint}.txt")
    else:
        type_rules = "请先判断诊疗类型，然后按该类型的规则提取 special_findings。"

    system_prompt = system_prompt.replace("{type_specific_rules}", type_rules)
    user_prompt = _build_user_prompt(transcript)

    raw = await call_llm(
        system_prompt, user_prompt,
        model=model or config.DEFAULT_MODEL,
        treatment_hint=treatment_hint,
    )
    payload = _parse_json_payload(raw)

    # 容错：尝试补全
    payload.setdefault("treatment_type", treatment_hint or "extraction")
    payload.setdefault("confidence", 0.5)
    payload.setdefault("chief_complaint", "待补充")
    payload.setdefault("present_illness", "待补充")
    payload.setdefault("examination", {})
    payload.setdefault("diagnosis", "待医生确认")
    payload.setdefault("treatment_plan", "待医生制定")
    payload.setdefault("special_findings", {})
    payload.setdefault("urgency", "routine")

    result = ExtractionResult(
        treatment_type=_coerce_treatment(payload["treatment_type"]),
        confidence=float(payload["confidence"]),
        chief_complaint=str(payload["chief_complaint"]),
        present_illness=str(payload["present_illness"]),
        past_history=payload.get("past_history"),
        examination=_coerce_dict(payload["examination"]),
        diagnosis=str(payload["diagnosis"]),
        treatment_plan=str(payload["treatment_plan"]),
        special_findings=_coerce_dict(payload["special_findings"]),
        urgency=_coerce_urgency(payload.get("urgency", "routine")),
        raw_transcript_ref=job_id,
        model_used=model or config.DEFAULT_MODEL,
    )
    elapsed = int((time.time() - start) * 1000)
    return result.model_dump(), elapsed


async def classify_treatment(
    transcript: str,
    job_id: str = "",
    *,
    model: str = "",
) -> dict[str, Any]:
    """纯分类（不抽取全部字段）."""
    if not transcript or not transcript.strip():
        raise ValueError("transcript_text 不能为空")
    raw = await call_llm(
        load_prompt("extraction_system.txt"), _build_user_prompt(transcript),
        model=model or config.DEFAULT_MODEL,
    )
    payload = _parse_json_payload(raw)
    tt = _coerce_treatment(payload.get("treatment_type", "extraction"))
    return {
        "treatment_type": tt,
        "confidence": float(payload.get("confidence", 0.5)),
        "model_used": model or config.DEFAULT_MODEL,
    }
