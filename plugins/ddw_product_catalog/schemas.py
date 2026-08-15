from __future__ import annotations

from typing import List, Optional

"""DDW 产品与插件目录插件 Pydantic schemas。"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 创建
# ---------------------------------------------------------------------------


class ProductCreateReq(BaseModel):
    """新建产品请求。"""

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")
    code: str = Field(..., min_length=1, max_length=50, description="产品编码（全局唯一）")
    name: str = Field(..., min_length=1, max_length=200, description="产品名称")
    product_type: str = Field(
        ...,
        min_length=1,
        max_length=30,
        description="产品类型：package / plugin / service / token",
    )
    description: Optional[str] = Field(None, description="产品描述")
    unit_price: Decimal = Field(..., ge=0, description="单价（>= 0）")
    unit: str = Field("套/年", max_length=20, description="单位（套/年、套/月、个、次等）")
    version: Optional[str] = Field(None, max_length=20, description="版本号（v1.0.0）")
    metadata_json: Optional[dict] = Field(None, description="扩展元数据 JSON")
    created_by: Optional[int] = Field(None, description="创建人 user_id")


# ---------------------------------------------------------------------------
# 更新（全字段可选）
# ---------------------------------------------------------------------------


class ProductUpdateReq(BaseModel):
    """更新产品请求。"""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    product_type: Optional[str] = Field(None, min_length=1, max_length=30)
    description: Optional[str] = None
    unit_price: Optional[Decimal] = Field(None, ge=0)
    unit: Optional[str] = Field(None, max_length=20)
    version: Optional[str] = Field(None, max_length=20)
    is_active: Optional[bool] = None
    metadata_json: Optional[dict] = None


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------


class ProductResp(BaseModel):
    """产品响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    code: str
    name: str
    product_type: str
    description: Optional[str] = None
    unit_price: Decimal
    unit: str
    version: Optional[str] = None
    is_active: bool
    metadata_json: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[int] = None


class ProductListResp(BaseModel):
    """分页列表响应。"""

    total: int
    page: int
    page_size: int
    items: List[ProductResp]


class ProductStatsResp(BaseModel):
    """产品统计概览。"""

    total: int
    active: int
    inactive: int
    by_product_type: dict[str, int]


__all__ = [
    "ProductCreateReq",
    "ProductListResp",
    "ProductResp",
    "ProductStatsResp",
    "ProductUpdateReq",
]
