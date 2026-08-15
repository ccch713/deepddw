"""DDW 投标标书插件 Pydantic schemas。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 项目
# ---------------------------------------------------------------------------


class ProjectCreateReq(BaseModel):
    project_name: str = Field(..., min_length=1, max_length=200)
    client_name: Optional[str] = None
    bid_deadline: Optional[datetime] = None
    project_type: Optional[str] = None
    estimated_amount: Optional[float] = None
    notes: Optional[str] = None
    tenant_id: int = 1


class ProjectUpdateReq(BaseModel):
    project_name: Optional[str] = None
    client_name: Optional[str] = None
    bid_deadline: Optional[datetime] = None
    project_type: Optional[str] = None
    estimated_amount: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class ProjectResp(BaseModel):
    id: int
    tenant_id: int
    project_name: str
    client_name: Optional[str] = None
    bid_deadline: Optional[datetime] = None
    project_type: Optional[str] = None
    estimated_amount: Optional[float] = None
    status: str
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProjectListResp(BaseModel):
    total: int
    items: List[ProjectResp]


# ---------------------------------------------------------------------------
# 标书
# ---------------------------------------------------------------------------


class GenerateReq(BaseModel):
    doc_type: str = "技术标"
    style: str = "标准"
    title: Optional[str] = None
    extra_requirements: Optional[str] = None
    template_id: Optional[int] = None
    mode: str = Field(
        "auto",
        pattern="^(auto|important|skeleton|legacy)$",
        description="auto=全流程（C+D+E）| important=渐进式披露 | skeleton=仅大纲 | legacy=旧版",
    )


class DocumentUpdateReq(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    style: Optional[str] = None


class DocumentResp(BaseModel):
    id: int
    bid_project_id: int
    doc_type: str
    style: str
    title: Optional[str] = None
    content: str
    version: int
    status: str
    review_notes: Optional[str] = None
    review_score: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DocumentListResp(BaseModel):
    total: int
    items: List[DocumentResp]


class RefineReq(BaseModel):
    """标书风格修饰请求（脱敏命名）。"""
    style: str = Field(..., description="目标风格：标准/保守/激进/创新型")
    instructions: Optional[str] = Field(None, description="额外修饰指令")


class RefineResp(BaseModel):
    document_id: int
    style: str
    version_before: int
    version_after: int
    diff_summary: str
    new_document_id: Optional[int] = None


class ReviewReq(BaseModel):
    check_items: Optional[List[str]] = None  # 自定义审查项；空则用默认


class ReviewIssue(BaseModel):
    severity: str  # info/warn/error
    category: str
    message: str
    location: Optional[str] = None


class ReviewResp(BaseModel):
    document_id: int
    score: float
    issues: List[ReviewIssue]
    summary: str
    suggestions: List[str]


class ApproveReq(BaseModel):
    approver: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# 模板
# ---------------------------------------------------------------------------


class TemplateCreateReq(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    doc_type: str = "技术标"
    content: str = ""
    is_default: bool = False
    description: Optional[str] = None
    tenant_id: int = 1


class TemplateUpdateReq(BaseModel):
    name: Optional[str] = None
    doc_type: Optional[str] = None
    content: Optional[str] = None
    is_default: Optional[bool] = None
    description: Optional[str] = None


class TemplateResp(BaseModel):
    id: int
    tenant_id: int
    name: str
    doc_type: str
    content: str
    is_default: bool
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TemplateListResp(BaseModel):
    total: int
    items: List[TemplateResp]


# ---------------------------------------------------------------------------
# 知识库 & 多阶段 & 渐进式披露（C+D+E+F 方案新增）
# ---------------------------------------------------------------------------


class KnowledgeBootstrapReq(BaseModel):
    """知识库学习触发请求。"""
    folder: str = Field(..., min_length=1, max_length=500, description="历史标书文件夹路径")
    tenant_id: int = 1


class KnowledgeBootstrapResp(BaseModel):
    run_id: int
    status: str
    total_files: int
    success_files: int
    failed_files: int
    total_chunks: int
    templates_extracted: int


class KnowledgeStatusResp(BaseModel):
    tenant_id: int
    kb_chunks: int
    docs_total: int
    docs_by_status: Dict[str, int]
    templates: List[Dict[str, Any]]
    last_run: Optional[Dict[str, Any]] = None


class AssessImportanceReq(BaseModel):
    """评估项目重要级别（F 方案）。"""
    is_first_with_client: bool = False
    user_marked: Optional[str] = Field(
        None, pattern="^(routine|important|critical)$"
    )


class AssessImportanceResp(BaseModel):
    level: str
    score: float
    reasons: List[str]
    recommended_mode: str
    message: str


class SectionItem(BaseModel):
    """章节记录。"""
    id: int
    bid_document_id: int
    section_index: int
    section_title: str
    outline_summary: Optional[str] = None
    content: Optional[str] = None
    rag_context: Optional[str] = None
    is_locked: int
    review_score: Optional[float] = None
    review_notes: Optional[str] = None


class SectionListResp(BaseModel):
    total: int
    items: List[SectionItem]


class SectionRegenerateReq(BaseModel):
    extra_instructions: Optional[str] = None
    style: Optional[str] = None


class SectionRegenerateResp(BaseModel):
    section_id: int
    new_content: str
    rag_hits: int
    locked: bool


class PlanResp(BaseModel):
    """阶段 1 大纲返回。"""
    doc_type: str
    style: str
    style_baseline: str
    sections: List[Dict[str, Any]]
    fact_sheet: Dict[str, Any]
    total_target_words: int


__all__ = [
    "ApproveReq",
    "AssessImportanceReq",
    "AssessImportanceResp",
    "DocumentListResp",
    "DocumentResp",
    "DocumentUpdateReq",
    "GenerateReq",
    "KnowledgeBootstrapReq",
    "KnowledgeBootstrapResp",
    "KnowledgeStatusResp",
    "PlanResp",
    "ProjectCreateReq",
    "ProjectListResp",
    "ProjectResp",
    "ProjectUpdateReq",
    "RefineReq",
    "RefineResp",
    "ReviewIssue",
    "ReviewReq",
    "ReviewResp",
    "SectionItem",
    "SectionListResp",
    "SectionRegenerateReq",
    "SectionRegenerateResp",
    "TemplateCreateReq",
    "TemplateListResp",
    "TemplateResp",
    "TemplateUpdateReq",
]
