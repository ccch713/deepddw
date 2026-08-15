"""插件市场论坛 API（F 项 — TASK_SPEC_F）。

端点（prefix /api/v1/forum）：
- GET  /plugins                插件论坛列表（裸数组）
- GET  /plugins/{name}         插件论坛首页（说明/版本/星/热议贴/最新贴）
- POST /plugins/{name}/star    打分 1-5（upsert）
- GET  /plugins/{name}/threads 帖子列表（sort=new|hot, page）
- POST /plugins/{name}/threads 发帖
- GET  /threads/{id}           帖子详情（views+1）+ 回复列表
- POST /threads/{id}/replies   回复
- POST /threads/{id}/pin       管理员置顶/取消
- GET  /search                 帖子搜索
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from core.auth.jwt import current_admin, current_user
from core.database.models import (
    ForumReply,
    ForumThread,
    PluginMarketItem,
    PluginStar,
)
from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

router = APIRouter(prefix="/api/v1/forum", tags=["forum"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class StarReq(BaseModel):
    stars: int = Field(..., ge=1, le=5)


class ThreadCreateReq(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    content: str = Field(..., min_length=1)


class ReplyCreateReq(BaseModel):
    content: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# 1. GET /plugins — 插件论坛列表（裸数组）
# ---------------------------------------------------------------------------


@router.get("/plugins")
async def list_forum_plugins(user: Dict[str, Any] = Depends(current_user)) -> list:
    """插件论坛列表（裸数组，含标题/分类/星/热议数/最新贴/分级）。"""
    # 读取插件分级（manifest tier）：目录名 + 连字符变体双 key
    tier_map: Dict[str, str] = {}
    try:
        plugins_dir = Path(__file__).resolve().parent.parent.parent / "plugins"
        for mf in sorted(plugins_dir.glob("*/manifest.yaml")):
            try:
                m = yaml.safe_load(mf.read_text(encoding="utf-8")) or {}
            except Exception:  # noqa: BLE001
                m = {}
            dname = mf.parent.name
            tier = str(m.get("tier", "beta") or "beta")
            tier_map[dname] = tier
            tier_map[dname.replace("_", "-")] = tier
    except Exception:  # noqa: BLE001
        pass

    async with session_scope() as session, bypass_tenant_filter():
        items = (await session.execute(
            select(PluginMarketItem).order_by(PluginMarketItem.category, PluginMarketItem.plugin_name)
        )).scalars().all()

        result = []
        for item in items:
            # 热议贴数（replies_count >= 5）
            hot_count = await session.scalar(
                select(func.count(ForumThread.id)).where(
                    ForumThread.plugin_name == item.plugin_name,
                    ForumThread.is_hot.is_(True),
                )
            ) or 0
            # 最新贴时间
            latest = await session.scalar(
                select(ForumThread.created_at)
                .where(ForumThread.plugin_name == item.plugin_name)
                .order_by(ForumThread.created_at.desc())
                .limit(1)
            )
            result.append({
                "plugin_name": item.plugin_name,
                "title": item.title,
                "category": item.category,
                "installs": item.installs,
                "stars": item.stars,
                "star_count": item.star_count,
                "updated_at": item.updated_at,
                "hot_count": hot_count,
                "latest_thread_at": latest.isoformat() if latest else None,
                "tier": tier_map.get(item.plugin_name, "beta"),
                "price_cny": item.price_cny,
                "price_note": item.price_note,
            })
        return result


# ---------------------------------------------------------------------------
# 2. GET /plugins/{name} — 插件论坛首页
# ---------------------------------------------------------------------------


@router.get("/plugins/{name}")
async def get_plugin_forum(name: str, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    """插件论坛首页：说明/版本/星/热议贴(前5)/最新贴(前10)。"""
    async with session_scope() as session, bypass_tenant_filter():
        item = (await session.execute(
            select(PluginMarketItem).where(PluginMarketItem.plugin_name == name)
        )).scalar_one_or_none()
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="插件不存在")

        # 热议贴（置顶或 is_hot，前 5）
        hot_threads = (await session.execute(
            select(ForumThread)
            .where(ForumThread.plugin_name == name, or_(ForumThread.is_pinned.is_(True), ForumThread.is_hot.is_(True)))
            .order_by(ForumThread.replies_count.desc())
            .limit(5)
        )).scalars().all()

        # 最新贴（前 10）
        recent_threads = (await session.execute(
            select(ForumThread)
            .where(ForumThread.plugin_name == name)
            .order_by(ForumThread.created_at.desc())
            .limit(10)
        )).scalars().all()

        def _thread_dict(t: ForumThread) -> dict:
            return {
                "id": t.id,
                "title": t.title,
                "author_name": t.author_name,
                "views": t.views,
                "replies_count": t.replies_count,
                "is_pinned": t.is_pinned,
                "is_hot": t.is_hot,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }

        return {
            "plugin_name": item.plugin_name,
            "title": item.title,
            "category": item.category,
            "installs": item.installs,
            "stars": item.stars,
            "star_count": item.star_count,
            "updated_at": item.updated_at,
            "hot_threads": [_thread_dict(t) for t in hot_threads],
            "recent_threads": [_thread_dict(t) for t in recent_threads],
        }


# ---------------------------------------------------------------------------
# 3. POST /plugins/{name}/star — 打分（upsert）
# ---------------------------------------------------------------------------


@router.post("/plugins/{name}/star")
async def star_plugin(name: str, req: StarReq, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    """打分 1-5（upsert），更新 plugin_market_items 平均星。"""
    async with session_scope() as session, bypass_tenant_filter():
        item = (await session.execute(
            select(PluginMarketItem).where(PluginMarketItem.plugin_name == name)
        )).scalar_one_or_none()
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="插件不存在")

        existing = (await session.execute(
            select(PluginStar).where(
                PluginStar.plugin_name == name,
                PluginStar.user_id == user["user_id"],
            )
        )).scalar_one_or_none()

        if existing is not None:
            existing.stars = req.stars
        else:
            session.add(PluginStar(
                plugin_name=name,
                user_id=user["user_id"],
                stars=req.stars,
            ))

        # 重新计算平均星
        all_stars = (await session.execute(
            select(PluginStar.stars).where(PluginStar.plugin_name == name)
        )).scalars().all()
        # 包含本次打分（新值已在 session 中）
        star_values = []
        for s in all_stars:
            if isinstance(s, (int, float)):
                star_values.append(s)
        # 如果 existing 被更新，all_stars 可能还是旧值，需手动替换
        if existing is not None:
            star_values = [req.stars if (existing.user_id == existing.user_id and i == len(star_values) - 1) else s for i, s in enumerate(star_values)]
        # 简化：重新查一次
        await session.flush()
        star_values = list((await session.execute(
            select(PluginStar.stars).where(PluginStar.plugin_name == name)
        )).scalars().all())

        avg = sum(star_values) / len(star_values) if star_values else 0.0
        item.stars = round(avg, 1)
        item.star_count = len(star_values)
        await session.commit()

        return {"plugin_name": name, "stars": req.stars, "avg_stars": item.stars, "star_count": item.star_count}


# ---------------------------------------------------------------------------
# 4. GET /plugins/{name}/threads — 帖子列表
# ---------------------------------------------------------------------------


@router.get("/plugins/{name}/threads")
async def list_threads(
    name: str,
    sort: str = Query("new", pattern="^(new|hot)$"),
    page: int = Query(1, ge=1),
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    """帖子列表（分页，{items, total, page}）。"""
    page_size = 20
    async with session_scope() as session, bypass_tenant_filter():
        base_q = select(ForumThread).where(ForumThread.plugin_name == name)
        total = await session.scalar(
            select(func.count()).select_from(base_q.subquery())
        ) or 0

        if sort == "hot":
            order = ForumThread.is_pinned.desc(), ForumThread.replies_count.desc(), ForumThread.created_at.desc()
        else:
            order = ForumThread.is_pinned.desc(), ForumThread.created_at.desc()

        offset = (page - 1) * page_size
        threads = (await session.execute(
            base_q.order_by(*order).offset(offset).limit(page_size)
        )).scalars().all()

        return {
            "items": [
                {
                    "id": t.id,
                    "title": t.title,
                    "author_name": t.author_name,
                    "views": t.views,
                    "replies_count": t.replies_count,
                    "is_pinned": t.is_pinned,
                    "is_hot": t.replies_count >= 5,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in threads
            ],
            "total": total,
            "page": page,
        }


# ---------------------------------------------------------------------------
# 5. POST /plugins/{name}/threads — 发帖
# ---------------------------------------------------------------------------


@router.post("/plugins/{name}/threads", status_code=status.HTTP_201_CREATED)
async def create_thread(
    name: str, req: ThreadCreateReq, user: Dict[str, Any] = Depends(current_user)
) -> Dict[str, Any]:
    """发帖。"""
    async with session_scope() as session, bypass_tenant_filter():
        item = (await session.execute(
            select(PluginMarketItem).where(PluginMarketItem.plugin_name == name)
        )).scalar_one_or_none()
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="插件不存在")

        author_name = user.get("raw", {}).get("name", "") or f"user_{user['user_id']}"
        thread = ForumThread(
            plugin_name=name,
            title=req.title,
            content=req.content,
            author_id=user["user_id"],
            author_name=author_name,
        )
        session.add(thread)
        await session.commit()
        await session.refresh(thread)

        return {
            "id": thread.id,
            "plugin_name": name,
            "title": thread.title,
            "author_name": thread.author_name,
            "created_at": thread.created_at.isoformat() if thread.created_at else None,
        }


# ---------------------------------------------------------------------------
# 6. GET /threads/{id} — 帖子详情（views+1）+ 回复列表
# ---------------------------------------------------------------------------


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: int, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    """帖子详情（views+1）+ 回复列表。"""
    async with session_scope() as session, bypass_tenant_filter():
        thread = (await session.execute(
            select(ForumThread).where(ForumThread.id == thread_id)
        )).scalar_one_or_none()
        if thread is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帖子不存在")

        thread.views += 1
        await session.flush()

        replies = (await session.execute(
            select(ForumReply)
            .where(ForumReply.thread_id == thread_id)
            .order_by(ForumReply.created_at)
        )).scalars().all()

        await session.commit()

        return {
            "id": thread.id,
            "plugin_name": thread.plugin_name,
            "title": thread.title,
            "content": thread.content,
            "author_name": thread.author_name,
            "views": thread.views,
            "replies_count": thread.replies_count,
            "is_pinned": thread.is_pinned,
            "is_hot": thread.is_hot,
            "created_at": thread.created_at.isoformat() if thread.created_at else None,
            "replies": [
                {
                    "id": r.id,
                    "author_name": r.author_name,
                    "content": r.content,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in replies
            ],
        }


# ---------------------------------------------------------------------------
# 7. POST /threads/{id}/replies — 回复
# ---------------------------------------------------------------------------


@router.post("/threads/{thread_id}/replies", status_code=status.HTTP_201_CREATED)
async def create_reply(
    thread_id: int, req: ReplyCreateReq, user: Dict[str, Any] = Depends(current_user)
) -> Dict[str, Any]:
    """回复帖子。"""
    async with session_scope() as session, bypass_tenant_filter():
        thread = (await session.execute(
            select(ForumThread).where(ForumThread.id == thread_id)
        )).scalar_one_or_none()
        if thread is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帖子不存在")

        author_name = user.get("raw", {}).get("name", "") or f"user_{user['user_id']}"
        reply = ForumReply(
            thread_id=thread_id,
            author_id=user["user_id"],
            author_name=author_name,
            content=req.content,
        )
        session.add(reply)
        thread.replies_count += 1
        if thread.replies_count >= 5:
            thread.is_hot = True
        await session.commit()
        await session.refresh(reply)

        return {
            "id": reply.id,
            "thread_id": thread_id,
            "author_name": reply.author_name,
            "created_at": reply.created_at.isoformat() if reply.created_at else None,
        }


# ---------------------------------------------------------------------------
# 8. POST /threads/{id}/pin — 管理员置顶/取消
# ---------------------------------------------------------------------------


@router.post("/threads/{thread_id}/pin")
async def pin_thread(
    thread_id: int, user: Dict[str, Any] = Depends(current_admin)
) -> Dict[str, Any]:
    """管理员置顶/取消置顶。"""
    async with session_scope() as session, bypass_tenant_filter():
        thread = (await session.execute(
            select(ForumThread).where(ForumThread.id == thread_id)
        )).scalar_one_or_none()
        if thread is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帖子不存在")

        thread.is_pinned = not thread.is_pinned
        await session.commit()

        return {"id": thread.id, "is_pinned": thread.is_pinned}


# ---------------------------------------------------------------------------
# 9. GET /search — 帖子搜索
# ---------------------------------------------------------------------------


@router.get("/search")
async def search_threads(
    q: str = Query("", min_length=0),
    user: Dict[str, Any] = Depends(current_user),
) -> list:
    """帖子搜索（title/content LIKE，裸数组）。"""
    if not q.strip():
        return []

    pattern = f"%{q.strip()}%"
    async with session_scope() as session, bypass_tenant_filter():
        threads = (await session.execute(
            select(ForumThread)
            .where(or_(ForumThread.title.like(pattern), ForumThread.content.like(pattern)))
            .order_by(ForumThread.created_at.desc())
            .limit(50)
        )).scalars().all()

        return [
            {
                "id": t.id,
                "plugin_name": t.plugin_name,
                "title": t.title,
                "author_name": t.author_name,
                "views": t.views,
                "replies_count": t.replies_count,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in threads
        ]


__all__ = ["router"]
