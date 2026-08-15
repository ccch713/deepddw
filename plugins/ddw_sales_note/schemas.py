from __future__ import annotations

"""DDW 拜访与沟通记录插件 Pydantic schemas。"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 创建
# ---------------------------------------------------------------------------


class SalesNoteCreateReq(BaseModel):
    """新建拜访/沟通记录请求。"""

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")
    user_id: Optional[int] = Field(None, description="记录人 user_id（为空则默认 created_by）")
    company_id: Optional[int] = Field(None, description="关联企业 ID")
    contact_id: Optional[int] = Field(None, description="关联联系人 ID")
    opportunity_id: Optional[int] = Field(None, description="关联商机 ID")
    note_type: str = Field(..., min_length=1, max_length=30, description="沟通类型")
    # visit / call / meeting / email / wechat
    title: Optional[str] = Field(None, max_length=200)
    content: str = Field(..., min_length=1, description="沟通内容（必填）")
    visit_date: Optional[datetime] = Field(None, description="沟通实际发生时间")
    tags: Optional[List[str]] = None
    attachments: Optional[List[str]] = None
    created_by: Optional[int] = Field(None, description="创建人 user_id")


# ---------------------------------------------------------------------------
# 更新（全字段可选）
# ---------------------------------------------------------------------------


class SalesNoteUpdateReq(BaseModel):
    """更新记录请求。"""

    note_type: Optional[str] = Field(None, min_length=1, max_length=30)
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = Field(None, min_length=1)
    visit_date: Optional[datetime] = None
    user_id: Optional[int] = None
    company_id: Optional[int] = None
    contact_id: Optional[int] = None
    opportunity_id: Optional[int] = None
    tags: Optional[List[str]] = None
    attachments: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------


class SalesNoteResp(BaseModel):
    """单条记录响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    user_id: Optional[int] = None
    company_id: Optional[int] = None
    contact_id: Optional[int] = None
    opportunity_id: Optional[int] = None
    note_type: str
    title: Optional[str] = None
    content: str
    visit_date: Optional[datetime] = None
    tags: Optional[List[str]] = None
    attachments: Optional[List[str]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[int] = None


class SalesNoteListResp(BaseModel):
    """分页列表响应。"""

    total: int
    page: int
    page_size: int
    items: List[SalesNoteResp]


class SalesNoteStatsResp(BaseModel):
    """沟通记录统计概览。"""

    total: int
    by_note_type: dict[str, int]
    recent_30d: int
    # 最近 30 天内 visit_date 非空的记录数（基于沟通发生时间）


__all__ = [
    "SalesNoteCreateReq",
    "SalesNoteListResp",
    "SalesNoteResp",
    "SalesNoteStatsResp",
    "SalesNoteUpdateReq",
]
