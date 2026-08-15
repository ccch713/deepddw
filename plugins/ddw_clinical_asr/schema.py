"""DDW Clinical ASR - Schema 定义.

9 类诊疗类型枚举 + 通用 ExtractionResult 模型。
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TreatmentType(str, Enum):
    """口腔门诊 9 类诊疗类型."""

    ORTHODONTICS = "orthodontics"      # 正畸
    PULP_OPEN = "pulp_open"            # 开髓
    EXTRACTION = "extraction"          # 拔牙
    COSMETIC = "cosmetic"              # 医美（贴面/美白/树脂）
    ROOT_CANAL = "root_canal"          # 根管充填
    IMPLANT = "implant"                # 种植
    PROSTHESIS = "prosthesis"          # 修复（冠/桥/嵌体）
    PERIODONTAL = "periodontal"        # 牙周
    PEDIATRIC = "pediatric"            # 儿牙


TREATMENT_VALUES = tuple(t.value for t in TreatmentType)
URGENCY_VALUES = ("routine", "urgent", "emergency")


class ExtractionResult(BaseModel):
    """结构化抽取结果（9 类诊疗通用结构）."""

    treatment_type: TreatmentType
    confidence: float = Field(ge=0, le=1)
    chief_complaint: str = Field(description="主诉")
    present_illness: str = Field(description="现病史")
    past_history: Optional[str] = None
    examination: dict[str, Any] = Field(default_factory=dict, description="检查结果 key-value")
    diagnosis: str = Field(description="诊断")
    treatment_plan: str = Field(description="治疗计划")
    special_findings: dict[str, Any] = Field(default_factory=dict, description="诊疗类型特有字段")
    urgency: str = Field(default="routine", description="routine/urgent/emergency")
    raw_transcript_ref: str = Field(default="", description="关联的转写 job_id")
    model_used: str = Field(default="", description="使用的 LLM 模型标识")


class ClassifyResult(BaseModel):
    """纯分类结果（不抽取）."""

    treatment_type: TreatmentType
    confidence: float = Field(ge=0, le=1)
    model_used: str = ""


class ExtractRequest(BaseModel):
    transcript_text: str
    job_id: str = ""
    treatment_hint: Optional[str] = None


class ExtractResponse(BaseModel):
    status: str = "ok"
    result: ExtractionResult
    latency_ms: int = 0


class ClassifyRequest(BaseModel):
    transcript_text: str
    job_id: str = ""


class ClassifyResponse(BaseModel):
    status: str = "ok"
    result: ClassifyResult


class HealthResponse(BaseModel):
    plugin: str = "ddw_clinical_asr"
    version: str = "0.1.0"
    status: str = "ok"
    available_types: int = 9
    default_model: str = "MiniMax-M3"
