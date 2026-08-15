from __future__ import annotations

"""DDW 订单管理插件 API 路由。

API 端点（10 个）：
  健康检查：GET  /health
  订单 CRUD：POST /orders, GET /orders, GET /orders/stats
             GET /orders/{id}, PUT /orders/{id}, DELETE /orders/{id}
  状态机  ：POST /orders/{id}/confirm
             POST /orders/{id}/deliver
             POST /orders/{id}/complete
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .schemas import (
    OrderCancelReq,
    OrderCreateReq,
    OrderListResp,
    OrderStatsResp,
    OrderUpdateReq,
)
from .services import OrderService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造订单管理路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-order",
        tags=["ddw-order"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-order", "version": "1.0.0", "status": "ok"}

    # -----------------------------------------------------------------------
    # 订单 CRUD
    # -----------------------------------------------------------------------
    @router.post("/orders", response_model=dict, status_code=201)
    async def create_order(data: OrderCreateReq) -> dict:
        """新建订单（status=pending）。

        - 服务端自动生成 order_no（ORD-YYYYMMDD-NNN）
        - 服务端按 items 自动计算 total_amount
        - items 以 JSON 列存储
        """
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = OrderService(db)
                try:
                    return await svc.create(data)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))

    @router.get("/orders", response_model=OrderListResp)
    async def list_orders(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页条数"),
        search: Optional[str] = Query(
            None, description="模糊搜索（单号 / 标题）"
        ),
        status: Optional[str] = Query(
            None, description="状态筛选（pending/confirmed/delivered/completed/cancelled）"
        ),
        company_id: Optional[int] = Query(None, description="按关联企业 ID 筛选"),
        contract_id: Optional[int] = Query(None, description="按关联合同 ID 筛选"),
    ) -> OrderListResp:
        """订单列表（分页 + 多维筛选 + 搜索）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = OrderService(db)
                return await svc.list(
                    page=page,
                    page_size=page_size,
                    search=search,
                    status=status,
                    company_id=company_id,
                    contract_id=contract_id,
                )

    @router.get("/orders/stats", response_model=OrderStatsResp)
    async def order_stats() -> OrderStatsResp:
        """订单统计概览。

        - 各状态计数
        - 所有订单 total_amount 之和
        - 已完成订单的 total_amount 之和
        """
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = OrderService(db)
                return await svc.stats()

    @router.get("/orders/{order_id}", response_model=dict)
    async def get_order(order_id: int) -> dict:
        """订单详情（含 items）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = OrderService(db)
                result = await svc.get(order_id)
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"order {order_id} not found",
                    )
                return result

    @router.put("/orders/{order_id}", response_model=dict)
    async def update_order(order_id: int, data: OrderUpdateReq) -> dict:
        """更新订单。

        - 字段级更新（model_dump(exclude_unset=True)）
        - 若 ``items`` 在请求中：整体替换并重算 total_amount
        - 限制：**仅 pending 状态可改**，其他状态返回 400
        """
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = OrderService(db)
                try:
                    result = await svc.update(order_id, data)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"order {order_id} not found",
                    )
                return result

    @router.delete("/orders/{order_id}", response_model=dict)
    async def cancel_order(order_id: int, data: OrderCancelReq) -> dict:
        """取消订单（pending / confirmed → cancelled，reason 必填）。

        - 非 pending/confirmed 状态返回 400
        - reason 缺省或为空由 Pydantic 校验（422）
        """
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = OrderService(db)
                try:
                    result = await svc.cancel(order_id, data)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"order {order_id} not found",
                    )
                return result

    # -----------------------------------------------------------------------
    # 状态机
    # -----------------------------------------------------------------------
    @router.post("/orders/{order_id}/confirm", response_model=dict)
    async def confirm_order(order_id: int) -> dict:
        """确认订单（pending → confirmed，confirmed_at=now）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = OrderService(db)
                try:
                    result = await svc.confirm(order_id)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"order {order_id} not found",
                    )
                return result

    @router.post("/orders/{order_id}/deliver", response_model=dict)
    async def deliver_order(order_id: int) -> dict:
        """交付订单（confirmed → delivered，delivered_at=now）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = OrderService(db)
                try:
                    result = await svc.deliver(order_id)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"order {order_id} not found",
                    )
                return result

    @router.post("/orders/{order_id}/complete", response_model=dict)
    async def complete_order(order_id: int) -> dict:
        """完成订单（delivered → completed，completed_at=now）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = OrderService(db)
                try:
                    result = await svc.complete(order_id)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"order {order_id} not found",
                    )
                return result

    return router


__all__ = ["build_router"]
