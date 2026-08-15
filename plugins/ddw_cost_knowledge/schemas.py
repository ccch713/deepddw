"""DDW 造价知识库 Pydantic schemas。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 文件
# ---------------------------------------------------------------------------


class DocumentUploadReq(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=200)
    file_content_b64: Optional[str] = None  # base64 编码的文件内容（可选，仅元数据模式可省）
    doc_type: str = "历史造价文件"
    project_name: Optional[str] = None
    project_type: Optional[str] = None
    total_cost: Optional[float] = None
    area: Optional[float] = None
    unit_price: Optional[float] = None
    notes: Optional[str] = None
    tenant_id: int = 1


class DocumentResp(BaseModel):
    id: int
    tenant_id: int
    file_name: str
    file_path: Optional[str] = None
    doc_type: str
    project_name: Optional[str] = None
    project_type: Optional[str] = None
    total_cost: Optional[float] = None
    area: Optional[float] = None
    unit_price: Optional[float] = None
    extracted_data: Optional[Dict[str, Any]] = None
    status: str
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DocumentListResp(BaseModel):
    total: int
    items: List[DocumentResp]


class ExtractResp(BaseModel):
    document_id: int
    status: str
    extracted_data: Optional[Dict[str, Any]] = None
    message: str = ""


# ---------------------------------------------------------------------------
# 检索
# ---------------------------------------------------------------------------


class SearchHit(BaseModel):
    document_id: int
    file_name: str
    doc_type: str
    project_name: Optional[str] = None
    project_type: Optional[str] = None
    total_cost: Optional[float] = None
    area: Optional[float] = None
    unit_price: Optional[float] = None
    score: float
    snippet: Optional[str] = None


class SearchResp(BaseModel):
    query: str
    total: int
    hits: List[SearchHit]


# ---------------------------------------------------------------------------
# 估算
# ---------------------------------------------------------------------------


class EstimateCreateReq(BaseModel):
    project_name: str = Field(..., min_length=1, max_length=200)
    project_type: str = Field(..., min_length=1, max_length=50)
    area: float = Field(..., gt=0)
    floor_count: Optional[int] = None
    structure_type: Optional[str] = None
    notes: Optional[str] = None
    tenant_id: int = 1


class EstimateResp(BaseModel):
    id: int
    tenant_id: int
    project_name: str
    project_type: str
    area: float
    floor_count: Optional[int] = None
    structure_type: Optional[str] = None
    estimate_result: Optional[Dict[str, Any]] = None
    reference_docs: Optional[List[int]] = None
    confidence: float
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------


class StatsResp(BaseModel):
    documents_total: int
    documents_by_type: Dict[str, int]
    documents_by_project_type: Dict[str, int]
    estimates_total: int
    avg_unit_price: float
    avg_total_cost: float


# ---------------------------------------------------------------------------
# 批量导入
# ---------------------------------------------------------------------------


class BatchImportItem(BaseModel):
    file_name: str
    doc_type: str = "历史造价文件"
    project_name: Optional[str] = None
    project_type: Optional[str] = None
    total_cost: Optional[float] = None
    area: Optional[float] = None
    unit_price: Optional[float] = None


class BatchImportReq(BaseModel):
    folder: str = Field(..., description="目标文件夹路径或标识")
    items: List[BatchImportItem] = Field(..., min_length=1)
    tenant_id: int = 1
    auto_extract: bool = False


class BatchImportResp(BaseModel):
    success: int
    failed: int
    document_ids: List[int]
    errors: List[Dict[str, Any]]


__all__ = [
    "BatchImportItem",
    "BatchImportReq",
    "BatchImportResp",
    "DocumentListResp",
    "DocumentResp",
    "DocumentUploadReq",
    "EstimateCreateReq",
    "EstimateResp",
    "ExtractResp",
    "SearchHit",
    "SearchResp",
    "StatsResp",
]
