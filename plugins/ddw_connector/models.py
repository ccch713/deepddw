"""DDW 连接器元数据发现框架 Pydantic 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 数据源
# ---------------------------------------------------------------------------


class DatasourceCreateReq(BaseModel):
    """注册数据源请求。"""

    name: str = Field(..., max_length=200, description="数据源名称")
    ds_type: str = Field(..., description="数据源类型：sql_readonly / api_openapi")
    conn_info: dict[str, Any] = Field(..., description="连接信息（V0.1 明文存储）")
    description: Optional[str] = Field(None, max_length=500)


class DatasourceResp(BaseModel):
    """数据源响应。"""

    id: int
    name: str
    ds_type: str
    description: Optional[str] = None
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# 元数据扫描
# ---------------------------------------------------------------------------


class FieldMeta(BaseModel):
    """字段级元数据。"""

    name: str
    field_type: str
    comment: Optional[str] = None
    nullable: bool = True
    is_primary_key: bool = False
    is_foreign_key: bool = False
    fk_ref_table: Optional[str] = None


class TableMeta(BaseModel):
    """表/资源级元数据。"""

    name: str
    row_count_estimate: Optional[int] = None
    comment: Optional[str] = None
    fields: list[FieldMeta] = []


class MetadataReport(BaseModel):
    """元数据扫描报告。"""

    datasource_id: int
    ds_type: str
    tables: list[TableMeta] = []
    scanned_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# 数据字典草稿
# ---------------------------------------------------------------------------


class DictionaryDraftResp(BaseModel):
    """数据字典草稿响应。"""

    id: int
    datasource_id: int
    table_name: str
    field_name: str
    field_type: str
    field_comment: Optional[str] = None
    perm_tag: str = "deny"
    status: str = "draft"
    confirmed_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DraftConfirmReq(BaseModel):
    """确认草稿请求。"""

    perm_tag: str = Field(..., description="权限标签：public / dept:<部门名> / role:<角色> / deny")
    confirmed_by: str = Field(..., max_length=100)


# ---------------------------------------------------------------------------
# 查询网关
# ---------------------------------------------------------------------------


class QueryReq(BaseModel):
    """查询网关请求。"""

    datasource_id: int
    user_perms: list[str] = Field(default_factory=list, description="用户权限标签列表")
    sql_or_api_path: str = Field(..., description="SQL 语句或 API 路径")
    params: dict[str, Any] = Field(default_factory=dict)


class QueryResult(BaseModel):
    """查询结果。"""

    columns: list[str] = []
    rows: list[list[Any]] = []
    row_count: int = 0
    error: Optional[str] = None
    detail: Optional[str] = None
