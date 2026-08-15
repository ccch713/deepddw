from __future__ import annotations

"""DDW 联系人管理插件 Pydantic schemas。"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 创建
# ---------------------------------------------------------------------------


class ContactCreateReq(BaseModel):
    """新建联系人请求。"""

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")
    company_id: Optional[int] = Field(
        None, ge=1, description="所属企业 ID（可空，独立联系人）"
    )
    name: str = Field(..., min_length=1, max_length=50, description="联系人姓名")
    phone: Optional[str] = Field(None, max_length=20, description="手机号")
    email: Optional[str] = Field(None, max_length=100, description="邮箱")
    position: Optional[str] = Field(None, max_length=50, description="职位")
    department: Optional[str] = Field(None, max_length=50, description="部门")
    wechat: Optional[str] = Field(None, max_length=50, description="微信号")
    tags: Optional[List[str]] = Field(default=None, description="标签列表")
    groups: Optional[List[str]] = Field(default=None, description="分组列表")
    is_primary: bool = Field(default=False, description="是否主联系人")
    notes: Optional[str] = Field(None, description="备注")


# ---------------------------------------------------------------------------
# 更新（全字段可选）
# ---------------------------------------------------------------------------


class ContactUpdateReq(BaseModel):
    """更新联系人请求。"""

    name: Optional[str] = Field(None, min_length=1, max_length=50)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)
    position: Optional[str] = Field(None, max_length=50)
    department: Optional[str] = Field(None, max_length=50)
    wechat: Optional[str] = Field(None, max_length=50)
    tags: Optional[List[str]] = None
    groups: Optional[List[str]] = None
    is_primary: Optional[bool] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    company_id: Optional[int] = Field(None, ge=1)


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------


class ContactResp(BaseModel):
    """联系人响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    company_id: Optional[int] = None
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    position: Optional[str] = None
    department: Optional[str] = None
    wechat: Optional[str] = None
    tags: Optional[List[str]] = None
    groups: Optional[List[str]] = None
    is_primary: bool = False
    notes: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[int] = None


class ContactListResp(BaseModel):
    """联系人分页列表响应。"""

    total: int
    page: int
    page_size: int
    items: List[ContactResp]


class ContactStatsResp(BaseModel):
    """联系人统计概览。"""

    total: int
    active: int
    inactive: int
    archived: int
    primary: int
    with_company: int
    independent: int  # 无 company_id
    by_company: dict[str, int]


__all__ = [
    "ContactCreateReq",
    "ContactListResp",
    "ContactResp",
    "ContactStatsResp",
    "ContactUpdateReq",
]
