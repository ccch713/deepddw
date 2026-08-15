from __future__ import annotations

from typing import Optional

"""DDW 产品与插件目录插件 API 路由。

API 端点（8 个）：
  健康：GET  /health
  CRUD : POST /products, GET /products, GET /products/{id}, PUT /products/{id}
  软删：DELETE /products/{id}                          （is_active=False）
  搜索：GET /products/search?q=
  统计：GET /products/stats
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .schemas import (
    ProductCreateReq,
    ProductListResp,
    ProductStatsResp,
    ProductUpdateReq,
)
from .services import ProductService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造产品与插件目录路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-product-catalog",
        tags=["ddw-product-catalog"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-product-catalog", "version": "1.0.0", "status": "ok"}

    # -----------------------------------------------------------------------
    # CRUD
    # -----------------------------------------------------------------------

    @router.post("/products", response_model=dict, status_code=201)
    async def create_product(data: ProductCreateReq) -> dict:
        """新建产品。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = ProductService(db)
            try:
                return await svc.create(data)
            except ValueError as e:
                # 重复 code 走 409（语义冲突），类型非法走 400
                msg = str(e)
                if "已存在" in msg:
                    raise HTTPException(status_code=409, detail=msg)
                raise HTTPException(status_code=400, detail=msg)

    @router.get("/products", response_model=ProductListResp)
    async def list_products(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页条数"),
        product_type: Optional[str] = Query(
            None, description="产品类型（package/plugin/service/token）"
        ),
        is_active: Optional[bool] = Query(None, description="激活状态筛选"),
    ) -> ProductListResp:
        """产品列表（分页 + 筛选：按 product_type/is_active）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = ProductService(db)
            return await svc.list(
                page=page,
                page_size=page_size,
                product_type=product_type,
                is_active=is_active,
            )

    @router.get("/products/search", response_model=list)
    async def search_products(
        q: str = Query(..., min_length=1, description="搜索关键词（code/name 模糊）"),
        limit: int = Query(20, ge=1, le=50),
    ) -> list:
        """按 code/name 模糊搜索（仅返回 is_active=True）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = ProductService(db)
            return await svc.search(q=q, limit=limit)

    @router.get("/products/stats", response_model=ProductStatsResp)
    async def product_stats() -> ProductStatsResp:
        """产品统计概览：total/active/inactive + by_product_type。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = ProductService(db)
            return await svc.stats()

    @router.get("/products/{product_id}", response_model=dict)
    async def get_product(product_id: int) -> dict:
        """产品详情。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = ProductService(db)
            result = await svc.get(product_id)
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"product {product_id} not found",
                )
            return result

    @router.put("/products/{product_id}", response_model=dict)
    async def update_product(
        product_id: int, data: ProductUpdateReq
    ) -> dict:
        """更新产品。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = ProductService(db)
            try:
                result = await svc.update(product_id, data)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"product {product_id} not found",
                )
            return result

    @router.delete("/products/{product_id}", response_model=dict)
    async def deactivate_product(product_id: int) -> dict:
        """软删除产品（is_active=False）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = ProductService(db)
            result = await svc.deactivate(product_id)
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"product {product_id} not found",
                )
            return result

    return router


__all__ = ["build_router"]
