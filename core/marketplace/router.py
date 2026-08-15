"""FastAPI 路由 — 插件市场 API。

提供插件列表、详情、安装/卸载/启停、评价等完整市场 API。
所有端点挂载在 /api/v1/plugins 路径下。
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from core.database.factory import get_engine_factory
from core.marketplace.models import PluginInstall, PluginListing, PluginReview
from core.marketplace.plugin_installer import get_plugin_installer
from core.marketplace.plugin_market import (
    PluginActionResponse,
    PluginCategory,
    PluginDetailResponse,
    PluginInstalledResponse,
    PluginInstallRequest,
    PluginListingResponse,
    PluginMarketStats,
    PluginReviewCreate,
    PluginReviewResponse,
    PluginStatus,
    PluginVersionInfo,
)
from core.marketplace.plugin_registry import get_plugin_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plugins", tags=["marketplace"])


# ---------------------------------------------------------------------------
# 市场列表 API
# ---------------------------------------------------------------------------


@router.get("", summary="获取插件市场列表")
async def list_plugins(
    category: Optional[PluginCategory] = Query(None, description="按分类过滤"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
) -> dict:
    """获取插件市场列表，支持分类过滤和关键词搜索。"""
    registry = get_plugin_registry()

    # 获取已安装插件状态
    installed_names = await _get_installed_names()

    # 扫描并过滤
    listings = registry.get_plugin_listings(category=category, search=search)

    # 分页
    total = len(listings)
    start = (page - 1) * page_size
    end = start + page_size
    page_listings = listings[start:end]

    # 构建响应
    items = []
    for listing in page_listings:
        item = PluginListingResponse(
            name=listing.name,
            version=listing.version,
            description=listing.description or "",
            author=listing.author,
            license=listing.license,
            category=listing.category,
            rating=listing.rating,
            downloads=listing.downloads,
            status=(
                PluginStatus.INSTALLED
                if listing.name in installed_names
                else PluginStatus.NOT_INSTALLED
            ),
            tags=listing.tags or [],
            engine=listing.engine,
            permissions=listing.permissions or [],
            dependencies=listing.dependencies or {},
            config_schema=listing.config_schema,
        )
        items.append(item)

    return {
        "items": [item.model_dump() for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/stats", summary="获取市场统计信息")
async def get_market_stats() -> dict:
    """获取插件市场统计信息。"""
    registry = get_plugin_registry()
    listings = registry.scan_local_plugins()

    installed_names = await _get_installed_names()
    enabled_names = await _get_enabled_names()

    # 统计分类
    categories: dict[str, int] = {}
    total_downloads = 0
    for listing in listings:
        cat = listing.category if isinstance(listing.category, str) else listing.category.value
        categories[cat] = categories.get(cat, 0) + 1
        total_downloads += listing.downloads

    stats = PluginMarketStats(
        total_plugins=len(listings),
        installed_plugins=len(installed_names),
        enabled_plugins=len(enabled_names),
        total_downloads=total_downloads,
        categories=categories,
    )
    return stats.model_dump()


@router.get("/installed", summary="获取已安装插件列表")
async def list_installed_plugins() -> dict:
    """获取当前实例已安装的所有插件。"""
    factory = get_engine_factory()
    async with factory.session("main") as session:
        result = await session.execute(
            select(PluginInstall).order_by(PluginInstall.installed_at.desc())
        )
        records = result.scalars().all()

    items = []
    for record in records:
        item = PluginInstalledResponse(
            name=record.plugin_name,
            version=record.version,
            enabled=record.enabled,
            installed_at=record.installed_at,
            isolation=record.isolation,
        )
        items.append(item.model_dump())

    return {"items": items, "total": len(items)}


@router.get("/available", summary="获取可安装插件列表")
async def list_available_plugins() -> dict:
    """获取尚未安装的可安装插件列表。"""
    registry = get_plugin_registry()
    installed_names = await _get_installed_names()

    listings = registry.scan_local_plugins()
    available = [l for l in listings if l.name not in installed_names]

    items = []
    for listing in available:
        item = PluginListingResponse(
            name=listing.name,
            version=listing.version,
            description=listing.description or "",
            author=listing.author,
            license=listing.license,
            category=listing.category,
            rating=listing.rating,
            downloads=listing.downloads,
            status=PluginStatus.NOT_INSTALLED,
            tags=listing.tags or [],
            engine=listing.engine,
            permissions=listing.permissions or [],
            dependencies=listing.dependencies or {},
            config_schema=listing.config_schema,
        )
        items.append(item.model_dump())

    return {"items": items, "total": len(items)}


# ---------------------------------------------------------------------------
# 插件详情 API
# ---------------------------------------------------------------------------


@router.get("/{name}", summary="获取插件详情")
async def get_plugin_detail(name: str) -> dict:
    """获取单个插件的详细信息，包含版本历史和评价。"""
    registry = get_plugin_registry()
    listing = registry.get_plugin_detail(name)
    if not listing:
        raise HTTPException(status_code=404, detail=f"插件 '{name}' 不存在")

    # 获取安装状态
    installed_names = await _get_installed_names()
    enabled_names = await _get_enabled_names()

    # 获取评价
    reviews = await _get_plugin_reviews(name)
    review_responses = []
    for review in reviews:
        review_responses.append(
            PluginReviewResponse(
                id=review.id,
                plugin_name=review.plugin_name,
                user_id=review.user_id,
                rating=review.rating,
                comment=review.comment,
                created_at=review.created_at,
            )
        )

    detail = PluginDetailResponse(
        name=listing.name,
        version=listing.version,
        description=listing.description or "",
        author=listing.author,
        license=listing.license,
        category=listing.category,
        rating=listing.rating,
        downloads=listing.downloads,
        status=(
            PluginStatus.ENABLED
            if name in enabled_names
            else PluginStatus.INSTALLED
            if name in installed_names
            else PluginStatus.NOT_INSTALLED
        ),
        enabled=name in enabled_names if name in installed_names else None,
        tags=listing.tags or [],
        engine=listing.engine,
        permissions=listing.permissions or [],
        dependencies=listing.dependencies or {},
        config_schema=listing.config_schema,
        reviews=review_responses,
        versions=[
            PluginVersionInfo(
                version=listing.version,
                released_at=listing.updated_at if hasattr(listing, "updated_at") else None,
            )
        ],
    )

    return detail.model_dump()


# ---------------------------------------------------------------------------
# 安装/卸载/启停 API
# ---------------------------------------------------------------------------


@router.post("/{name}/install", summary="安装插件")
async def install_plugin(
    name: str,
    body: Optional[PluginInstallRequest] = None,
) -> dict:
    """安装或升级指定插件。"""
    installer = get_plugin_installer()
    version = body.version if body else None
    force = body.force if body else False

    result = await installer.install_plugin(name, version=version, force=force)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return PluginActionResponse(
        success=True,
        message=result["message"],
        plugin_name=name,
        action="install",
    ).model_dump()


@router.post("/{name}/uninstall", summary="卸载插件")
async def uninstall_plugin(name: str) -> dict:
    """卸载指定插件。"""
    installer = get_plugin_installer()
    result = await installer.uninstall_plugin(name)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return PluginActionResponse(
        success=True,
        message=result["message"],
        plugin_name=name,
        action="uninstall",
    ).model_dump()


@router.post("/{name}/enable", summary="启用插件")
async def enable_plugin(name: str) -> dict:
    """启用指定插件。"""
    installer = get_plugin_installer()
    result = await installer.enable_plugin(name)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return PluginActionResponse(
        success=True,
        message=result["message"],
        plugin_name=name,
        action="enable",
    ).model_dump()


@router.post("/{name}/disable", summary="禁用插件")
async def disable_plugin(name: str) -> dict:
    """禁用指定插件。"""
    installer = get_plugin_installer()
    result = await installer.disable_plugin(name)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return PluginActionResponse(
        success=True,
        message=result["message"],
        plugin_name=name,
        action="disable",
    ).model_dump()


# ---------------------------------------------------------------------------
# 评价 API
# ---------------------------------------------------------------------------


@router.post("/{name}/reviews", summary="创建插件评价")
async def create_review(name: str, body: PluginReviewCreate) -> dict:
    """为插件创建评价。"""
    # 检查插件是否存在
    registry = get_plugin_registry()
    if not registry.get_plugin_detail(name):
        raise HTTPException(status_code=404, detail=f"插件 '{name}' 不存在")

    factory = get_engine_factory()
    async with factory.session("main") as session:
        review = PluginReview(
            plugin_name=name,
            user_id=body.user_id,
            rating=body.rating,
            comment=body.comment,
        )
        session.add(review)
        await session.flush()

        # 更新插件平均评分
        avg_result = await session.execute(
            select(func.avg(PluginReview.rating)).where(PluginReview.plugin_name == name)
        )
        avg_rating = avg_result.scalar() or 0.0

        listing_result = await session.execute(
            select(PluginListing).where(PluginListing.name == name)
        )
        listing = listing_result.scalar_one_or_none()
        if listing:
            listing.rating = float(avg_rating)

    return {
        "success": True,
        "message": "评价创建成功",
        "review_id": review.id,
        "average_rating": float(avg_rating),
    }


@router.get("/{name}/reviews", summary="获取插件评价列表")
async def list_reviews(
    name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    """获取指定插件的评价列表。"""
    reviews = await _get_plugin_reviews(name, page=page, page_size=page_size)

    items = []
    for review in reviews:
        items.append(
            PluginReviewResponse(
                id=review.id,
                plugin_name=review.plugin_name,
                user_id=review.user_id,
                rating=review.rating,
                comment=review.comment,
                created_at=review.created_at,
            ).model_dump()
        )

    return {"items": items, "total": len(items)}


@router.post("/refresh", summary="刷新注册表缓存")
async def refresh_registry() -> dict:
    """强制刷新插件注册表缓存。"""
    registry = get_plugin_registry()
    listings = registry.refresh_registry()
    return {
        "success": True,
        "message": f"注册表已刷新，发现 {len(listings)} 个插件",
        "total": len(listings),
    }


@router.post("/validate-manifest", summary="验证 manifest 合规性")
async def validate_manifest_endpoint(manifest: dict) -> dict:
    """验证插件 manifest.yaml 的合规性。"""
    installer = get_plugin_installer()
    result = installer.validate_manifest(manifest)
    return result


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------


async def _get_installed_names() -> set[str]:
    """获取所有已安装插件的名称集合。"""
    factory = get_engine_factory()
    async with factory.session("main") as session:
        result = await session.execute(select(PluginInstall.plugin_name))
        return set(result.scalars().all())


async def _get_enabled_names() -> set[str]:
    """获取所有已启用插件的名称集合。"""
    factory = get_engine_factory()
    async with factory.session("main") as session:
        result = await session.execute(
            select(PluginInstall.plugin_name).where(PluginInstall.enabled.is_(True))
        )
        return set(result.scalars().all())


async def _get_plugin_reviews(
    name: str,
    page: int = 1,
    page_size: int = 20,
) -> list[PluginReview]:
    """获取插件评价列表。"""
    factory = get_engine_factory()
    async with factory.session("main") as session:
        offset = (page - 1) * page_size
        result = await session.execute(
            select(PluginReview)
            .where(PluginReview.plugin_name == name)
            .order_by(PluginReview.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        return list(result.scalars().all())
