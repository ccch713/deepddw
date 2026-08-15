from __future__ import annotations

"""DDW 产品与插件目录插件业务逻辑层。"""

import builtins
import logging
from typing import Any, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Product
from .schemas import (
    ProductCreateReq,
    ProductListResp,
    ProductResp,
    ProductStatsResp,
    ProductUpdateReq,
)

logger = logging.getLogger(__name__)

# 产品类型白名单（与 manifest.yaml config_schema.product_types 保持一致）
ALLOWED_PRODUCT_TYPES = {"package", "plugin", "service", "token"}


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _product_to_dict(p: Product) -> dict[str, Any]:
    """ORM → dict（用于响应）。"""
    return {
        "id": p.id,
        "tenant_id": p.tenant_id,
        "code": p.code,
        "name": p.name,
        "product_type": p.product_type,
        "description": p.description,
        "unit_price": p.unit_price,
        "unit": p.unit,
        "version": p.version,
        "is_active": p.is_active,
        "metadata_json": p.metadata_json or {},
        "created_at": p.created_at,
        "updated_at": p.updated_at,
        "created_by": p.created_by,
    }


# ---------------------------------------------------------------------------
# 业务服务
# ---------------------------------------------------------------------------


class ProductService:
    """产品/插件目录业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ---------------------------------------------------------------------
    # 新建
    # ---------------------------------------------------------------------

    async def create(self, data: ProductCreateReq) -> dict[str, Any]:
        """新建产品。

        - ``code`` 全局唯一，重复时抛 ValueError
        - ``product_type`` 必须在白名单内
        """
        if data.product_type not in ALLOWED_PRODUCT_TYPES:
            raise ValueError(
                f"product_type '{data.product_type}' 不合法，允许值: "
                f"{sorted(ALLOWED_PRODUCT_TYPES)}"
            )

        existing = await self._get_by_code(data.code)
        if existing:
            raise ValueError(
                f"code '{data.code}' 已存在 (id={existing.id})"
            )

        product = Product(
            tenant_id=data.tenant_id,
            code=data.code,
            name=data.name,
            product_type=data.product_type,
            description=data.description,
            unit_price=data.unit_price,
            unit=data.unit,
            version=data.version,
            is_active=True,
            metadata_json=data.metadata_json or {},
            created_by=data.created_by,
        )
        self.db.add(product)
        await self.db.commit()
        await self.db.refresh(product)
        logger.info(
            "product created: id=%s code=%s name=%s",
            product.id,
            product.code,
            product.name,
        )
        return _product_to_dict(product)

    # ---------------------------------------------------------------------
    # 详情
    # ---------------------------------------------------------------------

    async def get(self, product_id: int) -> dict[str, Any] | None:
        """获取产品详情。"""
        product = await self.db.get(Product, product_id)
        if not product:
            return None
        return _product_to_dict(product)

    # ---------------------------------------------------------------------
    # 列表
    # ---------------------------------------------------------------------

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        product_type: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> ProductListResp:
        """产品列表（分页 + 多维筛选）。

        - ``product_type``: 按产品类型过滤（精确匹配）
        - ``is_active``: 按激活状态过滤（True/False/None=全部）
        """
        conditions = []
        if product_type:
            conditions.append(Product.product_type == product_type)
        if is_active is not None:
            conditions.append(Product.is_active == is_active)

        # 总数
        count_stmt = select(func.count(Product.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar_one()

        # 列表
        offset = (page - 1) * page_size
        list_stmt = (
            select(Product)
            .order_by(Product.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        if conditions:
            list_stmt = list_stmt.where(and_(*conditions))
        rows = (await self.db.execute(list_stmt)).scalars().all()

        return ProductListResp(
            total=total,
            page=page,
            page_size=page_size,
            items=[ProductResp(**_product_to_dict(p)) for p in rows],
        )

    # ---------------------------------------------------------------------
    # 更新
    # ---------------------------------------------------------------------

    async def update(
        self, product_id: int, data: ProductUpdateReq
    ) -> dict[str, Any] | None:
        """更新产品字段。

        - ``code`` 不通过 update 修改（防破坏唯一性 + 业务引用）
        - ``product_type`` 改值时需校验白名单
        """
        product = await self.db.get(Product, product_id)
        if not product:
            return None

        updates = data.model_dump(exclude_unset=True)
        updates.pop("code", None)  # 编码不通过 update 修改

        if "product_type" in updates and updates["product_type"] not in ALLOWED_PRODUCT_TYPES:
            raise ValueError(
                f"product_type '{updates['product_type']}' 不合法，允许值: "
                f"{sorted(ALLOWED_PRODUCT_TYPES)}"
            )

        for k, v in updates.items():
            setattr(product, k, v)
        await self.db.commit()
        await self.db.refresh(product)
        logger.info("product updated: id=%s code=%s", product.id, product.code)
        return _product_to_dict(product)

    # ---------------------------------------------------------------------
    # 软删除
    # ---------------------------------------------------------------------

    async def deactivate(self, product_id: int) -> dict[str, Any] | None:
        """软删除产品（is_active=False）。

        与 company_profile 的 archive（status=archived）不同：本表用布尔
        is_active 字段实现软删除，更轻量、索引友好。
        """
        product = await self.db.get(Product, product_id)
        if not product:
            return None
        product.is_active = False
        await self.db.commit()
        await self.db.refresh(product)
        logger.info("product soft-deleted (is_active=False): id=%s", product_id)
        return _product_to_dict(product)

    # ---------------------------------------------------------------------
    # 搜索
    # ---------------------------------------------------------------------

    async def search(self, q: str, limit: int = 20) -> builtins.list[dict[str, Any]]:
        """按 code/name 模糊搜索（用于自动补全）。"""
        like = f"%{q}%"
        stmt = (
            select(Product)
            .where(
                and_(
                    or_(Product.code.like(like), Product.name.like(like)),
                    Product.is_active.is_(True),
                )
            )
            .order_by(Product.id.desc())
            .limit(limit)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return [_product_to_dict(p) for p in rows]

    # ---------------------------------------------------------------------
    # 统计
    # ---------------------------------------------------------------------

    async def stats(self) -> ProductStatsResp:
        """统计概览：total/active/inactive + by_product_type。"""
        # 按 is_active
        by_active_rows = (
            await self.db.execute(
                select(Product.is_active, func.count(Product.id)).group_by(
                    Product.is_active
                )
            )
        ).all()
        # SQLite 返回 0/1，需映射回 bool
        by_active: dict[bool, int] = {}
        for is_active, cnt in by_active_rows:
            by_active[bool(is_active)] = cnt
        total = sum(by_active.values())
        active = by_active.get(True, 0)
        inactive = by_active.get(False, 0)

        # 按 product_type
        by_type_rows = (
            await self.db.execute(
                select(Product.product_type, func.count(Product.id)).group_by(
                    Product.product_type
                )
            )
        ).all()
        by_type = {t: cnt for t, cnt in by_type_rows}

        return ProductStatsResp(
            total=total,
            active=active,
            inactive=inactive,
            by_product_type=by_type,
        )

    # ----- 内部辅助 -----

    async def _get_by_code(self, code: str) -> Product | None:
        stmt = select(Product).where(Product.code == code)
        return (await self.db.execute(stmt)).scalar_one_or_none()


__all__ = ["ProductService"]
