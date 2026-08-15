"""Pydantic 数据模型"""

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
from datetime import datetime


# ── 安全法规问答 ──

class RegulationQuery(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    context: Optional[str] = Field(None)


class RegulationAnswer(BaseModel):
    question: str
    answer: str
    sources: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    rag_used: bool = Field(default=False)


# ── 隐患上报 ──

class HazardStatus(str, Enum):
    PENDING = "待处理"
    IN_PROGRESS = "整改中"
    CLOSED = "已闭环"


class HazardType(str, Enum):
    FIRE = "消防隐患"
    ELECTRICAL = "电气隐患"
    MECHANICAL = "机械隐患"
    CHEMICAL = "化学品隐患"
    ENVIRONMENT = "环境隐患"
    PERSONAL = "人员行为隐患"
    OTHER = "其他"


class HazardReportCreate(BaseModel):
    area: str = Field(..., min_length=1, max_length=100)
    hazard_type: HazardType
    description: str = Field(..., min_length=1, max_length=2000)
    image_urls: List[str] = Field(default_factory=list)
    reporter: str = Field(default="anonymous", max_length=50)


class HazardReport(BaseModel):
    id: int
    area: str
    hazard_type: HazardType
    description: str
    image_urls: List[str]
    reporter: str
    status: HazardStatus = HazardStatus.PENDING
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None


class HazardStatusUpdate(BaseModel):
    status: HazardStatus
    resolution_note: Optional[str] = Field(None, max_length=1000)


# ── 安全培训卡片 ──

class TrainingQuestion(BaseModel):
    id: int
    question: str
    options: List[str] = Field(..., min_length=2, max_length=6)
    correct_index: int = Field(ge=0)
    explanation: str
    category: str = Field(default="通用")
    difficulty: int = Field(ge=1, le=3, default=1)


class TrainingAnswer(BaseModel):
    question_id: int
    selected_index: int = Field(ge=0)


class TrainingResult(BaseModel):
    question_id: int
    correct: bool
    selected_index: int
    correct_index: int
    explanation: str


# ── 风险提示牌 ──

class RiskLevel(str, Enum):
    HIGH = "高风险"
    MEDIUM = "中风险"
    LOW = "低风险"


class WorkType(str, Enum):
    HOT_WORK = "动火作业"
    CONFINED_SPACE = "受限空间作业"
    HIGH_ALTITUDE = "高处作业"
    LIFTING = "吊装作业"
    BLIND_PLATE = "盲板抽堵作业"
    TEMPORARY_POWER = "临时用电作业"
    GROUND_EXCAVATION = "动土作业"
    ROAD_BLOCKING = "断路作业"
    PRESSURE_WORK = "带压作业"


class ControlMeasure(BaseModel):
    title: str
    description: str


class RiskBulletin(BaseModel):
    work_type: WorkType
    risk_level: RiskLevel
    hazards: List[str]
    control_measures: List[ControlMeasure]
    emergency_procedures: List[str]
    legal_references: List[str] = Field(default_factory=list)


# ── 法规语料 ──

class RegulationClause(BaseModel):
    clause_number: str
    summary: str
    applicable_scenario: Optional[str] = None


class RegulationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    code: str = Field(..., min_length=1, max_length=100)
    year: int = Field(ge=1949, le=2099)
    category: str = Field(default="法律", max_length=50)
    clauses: List[RegulationClause] = Field(default_factory=list)
    applicable_scenarios: List[str] = Field(default_factory=list)


class Regulation(BaseModel):
    id: int
    name: str
    code: str
    year: int
    category: str
    clauses: List[RegulationClause]
    applicable_scenarios: List[str]
    created_at: str


class RegulationSeedResult(BaseModel):
    inserted: int
    skipped: int
    total: int


# ── 通用 ──

class PluginHealth(BaseModel):
    plugin_name: str
    version: str
    status: str = "healthy"
    database_connected: bool = True
    regulation_count: int = 0
    hazard_count: int = 0
    question_count: int = 0
