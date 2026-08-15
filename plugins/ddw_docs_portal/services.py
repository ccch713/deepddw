"""产品文档栏目业务逻辑（deepDDW 开源裁剪版）。

相对商业仓 6.0 的变更：
- 删除对 ``ddw_doc_assistant``（内容存储/向量检索）的依赖：正文内联存储于
  ``docs_item.content``，检索为本地关键词评分（title/content LIKE + 命中加权）；
- 删除对 ``ddw_memory`` 四层记忆的依赖：publish/archive 时把摘要写入 deepDDW
  内置记忆（``core.knowledge.memory_put``，namespace=docs_portal），失败不阻塞；
- 单用户模型：无账号/租户体系，token 持有者即管理员（superadmin 语义）；
  tenant_id 保留为 0。
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import PLUGIN_NAME
from .models import (
    DOC_TYPES,
    VISIBILITY,
    DocCategory,
    DocItem,
    DocVersion,
)

logger = logging.getLogger(__name__)

_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)$")


def _bump_version(version: str) -> str:
    """小版本递增：v1.0 -> v1.1；v1.9 -> v2.0。"""
    m = _VERSION_RE.match(version)
    if not m:
        return "v1.1"
    major, minor = int(m.group(1)), int(m.group(2))
    minor += 1
    if minor > 9:
        major, minor = major + 1, 0
    return f"v{major}.{minor}"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DocsPortalService:
    """文档栏目核心服务（deepDDW 开源版）。"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ─── 可见性（单用户简化） ─────────────────────────────────────

    def _visible_docs_stmt(self, user: dict[str, Any]):
        """统一可见文档查询：
        - published：管理员（token 持有者）可见全部；普通用户仅 public
        - draft → 作者或管理员
        - archived 一律不在可见列表（历史通过 DocVersion 追溯）
        """
        uid = int(user.get("user_id") or 0)
        is_admin = (user.get("role") or "member") in ("superadmin", "admin", "owner")

        published_visible = and_(
            DocItem.status == "published",
            or_(
                DocItem.visibility == "public",
                and_(DocItem.visibility != "public", is_admin),
            ),
        )
        draft_visible = and_(
            DocItem.status == "draft",
            or_(DocItem.author_id == uid, is_admin),
        )
        return select(DocItem).where(or_(published_visible, draft_visible))

    def _assert_admin(self, user: dict[str, Any]) -> None:
        """写操作权限：deepDDW 单用户 = token 持有者即管理员。"""
        if (user.get("role") or "member") not in ("superadmin", "admin", "owner"):
            raise HTTPException(status_code=403, detail="需要管理员权限")

    def _assert_platform_superadmin(self, user: dict[str, Any], tenant_id: int) -> None:
        """平台级资源（tenant_id=0）仅 superadmin 可写（deepDDW 单用户默认满足）。"""
        if tenant_id == 0 and user.get("role") != "superadmin":
            raise HTTPException(status_code=403, detail="平台级文档仅 superadmin 可管理")

    async def _get_editable(self, doc_id: int, user: dict[str, Any]) -> DocItem:
        """可编辑文档：作者或管理员；单用户下 token 持有者即管理员。"""
        doc = (
            await self._db.execute(select(DocItem).where(DocItem.id == doc_id))
        ).scalar_one_or_none()
        if doc is None:
            raise HTTPException(status_code=404, detail="文档不存在")
        is_admin = (user.get("role") or "member") in ("superadmin", "admin", "owner")
        if doc.author_id != int(user.get("user_id") or 0) and not is_admin:
            raise HTTPException(status_code=403, detail="仅作者或管理员可编辑该文档")
        return doc

    # ─── 记忆联动（deepDDW 内置记忆，namespace=docs_portal） ──────

    def _memory_content(self, doc: DocItem) -> str:
        """记忆内容：摘要 + docs_url + version。"""
        docs_url = f"/ui/docs.html?id={doc.slug}"
        parts = [f"文档：{doc.title}（{doc.version}）", f"链接：{docs_url}"]
        if doc.summary:
            parts.append(f"摘要：{doc.summary}")
        return "\n".join(parts)

    async def _memory_upsert(
        self, doc: DocItem, *, archived: bool = False
    ) -> None:
        """把文档摘要写入 deepDDW 记忆（namespace=docs_portal）；失败不阻塞。"""
        try:
            from core.knowledge import memory_put

            tags = [f"docs_portal:{doc.id}"]
            if archived:
                tags.append("archived")
            memory_put(
                namespace="docs_portal",
                key=f"doc:{doc.id}",
                value=self._memory_content(doc),
                tags=tags,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("docs_portal: memory upsert failed for doc %s: %s", doc.id, exc)

    async def _publish_event(self, event: str, payload: dict[str, Any]) -> None:
        try:
            from core.events.bus import get_bus

            await get_bus().publish(event, payload, source=PLUGIN_NAME)
        except Exception as exc:  # noqa: BLE001
            logger.warning("docs_portal: event %s publish failed: %s", event, exc)

    async def _commit(self, obj) -> None:
        """flush + refresh：回填 server_default（created_at/updated_at）后再序列化。"""
        await self._db.flush()
        await self._db.refresh(obj)

    # ─── 目录树 ─────────────────────────────────────────────────

    async def list_categories_tree(self, user: dict[str, Any]) -> list[dict]:
        """目录树（deepDDW：全量）。"""
        rows = (
            await self._db.execute(
                select(DocCategory).order_by(DocCategory.sort_order.asc(), DocCategory.id.asc())
            )
        ).scalars().all()
        nodes = {c.id: self._category_to_dict(c) for c in rows}
        tree: list[dict] = []
        for c in rows:
            node = nodes[c.id]
            if c.parent_id and c.parent_id in nodes:
                nodes[c.parent_id].setdefault("children", []).append(node)
            else:
                tree.append(node)
        return tree

    async def create_category(
        self, data: Any, user: dict[str, Any]
    ) -> dict:
        """建分类（管理员）。"""
        self._assert_admin(user)
        tenant_id = 0
        exists = (
            await self._db.execute(
                select(DocCategory).where(
                    DocCategory.tenant_id == tenant_id,
                    DocCategory.slug == data.slug,
                )
            )
        ).scalar_one_or_none()
        if exists:
            raise HTTPException(status_code=409, detail=f"slug 已存在: {data.slug}")
        cat = DocCategory(
            tenant_id=tenant_id,
            parent_id=data.parent_id,
            name=data.name,
            slug=data.slug,
            sort_order=data.sort_order,
        )
        self._db.add(cat)
        await self._commit(cat)
        return self._category_to_dict(cat)

    async def update_category(
        self, category_id: int, data: Any, user: dict[str, Any]
    ) -> dict:
        """改分类（管理员）。"""
        self._assert_admin(user)
        cat = (
            await self._db.execute(select(DocCategory).where(DocCategory.id == category_id))
        ).scalar_one_or_none()
        if cat is None:
            raise HTTPException(status_code=404, detail="分类不存在")
        if data.name is not None:
            cat.name = data.name
        if data.slug is not None:
            exists = (
                await self._db.execute(
                    select(DocCategory).where(
                        DocCategory.tenant_id == cat.tenant_id,
                        DocCategory.slug == data.slug,
                        DocCategory.id != cat.id,
                    )
                )
            ).scalar_one_or_none()
            if exists:
                raise HTTPException(status_code=409, detail=f"slug 已存在: {data.slug}")
            cat.slug = data.slug
        if data.parent_id is not None:
            cat.parent_id = data.parent_id
        if data.sort_order is not None:
            cat.sort_order = data.sort_order
        await self._db.flush()
        return self._category_to_dict(cat)

    # ─── 文档 CRUD ──────────────────────────────────────────────

    async def list_docs(
        self,
        user: dict[str, Any],
        category_id: Optional[int] = None,
        doc_type: Optional[str] = None,
        visibility: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """文档列表（只返回当前用户可见文档）。"""
        stmt = self._visible_docs_stmt(user)
        if category_id is not None:
            stmt = stmt.where(DocItem.category_id == category_id)
        if doc_type:
            stmt = stmt.where(DocItem.doc_type == doc_type)
        if visibility and visibility in VISIBILITY:
            stmt = stmt.where(DocItem.visibility == visibility)

        count = (
            await self._db.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar() or 0
        total = int(count)
        rows = (
            await self._db.execute(
                stmt.order_by(DocItem.published_at.desc().nulls_last(), DocItem.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        return {
            "items": [self._doc_to_dict(d) for d in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def get_doc(self, doc_id: int, user: dict[str, Any]) -> dict:
        """文档详情：元数据 + 内联正文。"""
        uid = int(user.get("user_id") or 0)
        is_admin = (user.get("role") or "member") in ("superadmin", "admin", "owner")

        doc = (
            await self._db.execute(
                self._visible_docs_stmt(user).where(DocItem.id == doc_id)
            )
        ).scalar_one_or_none()
        if doc is None:
            # 归档语义：archived 文档作者/管理员可查（版本可追溯）
            raw = (
                await self._db.execute(select(DocItem).where(DocItem.id == doc_id))
            ).scalar_one_or_none()
            if raw is None:
                raise HTTPException(status_code=404, detail="文档不存在")
            if raw.status == "archived" and (is_admin or raw.author_id == uid):
                doc = raw
            elif raw.status == "draft" and raw.author_id != uid and not is_admin:
                raise HTTPException(status_code=403, detail="该文档为草稿，仅作者或管理员可见")
            else:
                raise HTTPException(status_code=404, detail="文档不存在")

        result = self._doc_to_dict(doc)
        result["content"] = doc.content or ""
        return result

    async def create_doc(self, data: Any, user: dict[str, Any]) -> dict:
        """新建文档：正文内联存储，元数据存 docs_item。"""
        self._assert_admin(user)
        tenant_id = 0
        if data.doc_type not in DOC_TYPES:
            raise HTTPException(status_code=422, detail=f"doc_type 必须是 {DOC_TYPES}")
        if data.visibility not in VISIBILITY:
            raise HTTPException(status_code=422, detail=f"visibility 必须是 {VISIBILITY}")

        exists = (
            await self._db.execute(
                select(DocItem).where(
                    DocItem.tenant_id == tenant_id, DocItem.slug == data.slug
                )
            )
        ).scalar_one_or_none()
        if exists:
            raise HTTPException(status_code=409, detail=f"slug 已存在: {data.slug}")

        doc = DocItem(
            tenant_id=tenant_id,
            category_id=data.category_id,
            title=data.title,
            slug=data.slug,
            doc_type=data.doc_type,
            visibility=data.visibility,
            status="draft",
            version=data.version or "v1.0",
            content=data.content,
            content_hash=_sha256(data.content),
            summary=data.summary,
            author_id=int(user.get("user_id") or 0),
        )
        self._db.add(doc)
        await self._commit(doc)
        return self._doc_to_dict(doc)

    async def update_doc(
        self, doc_id: int, data: Any, user: dict[str, Any]
    ) -> dict:
        """更新：内容变更时旧内容入 DocVersion → version 递增。"""
        doc = await self._get_editable(doc_id, user)

        if data.title is not None:
            doc.title = data.title
        if data.slug is not None:
            exists = (
                await self._db.execute(
                    select(DocItem).where(
                        DocItem.tenant_id == doc.tenant_id,
                        DocItem.slug == data.slug,
                        DocItem.id != doc.id,
                    )
                )
            ).scalar_one_or_none()
            if exists:
                raise HTTPException(status_code=409, detail=f"slug 已存在: {data.slug}")
            doc.slug = data.slug
        if data.category_id is not None:
            doc.category_id = data.category_id
        if data.doc_type:
            if data.doc_type not in DOC_TYPES:
                raise HTTPException(status_code=422, detail=f"doc_type 必须是 {DOC_TYPES}")
            doc.doc_type = data.doc_type
        if data.visibility:
            if data.visibility not in VISIBILITY:
                raise HTTPException(status_code=422, detail=f"visibility 必须是 {VISIBILITY}")
            doc.visibility = data.visibility
        if data.summary is not None:
            doc.summary = data.summary

        content_updated = data.content is not None
        if content_updated:
            old_content = doc.content
            self._db.add(
                DocVersion(
                    tenant_id=doc.tenant_id,
                    doc_id=doc.id,
                    version=doc.version,
                    change_note=data.version or "内容更新",
                    source_ref=_sha256(old_content),
                )
            )
            doc.content = data.content
            doc.content_hash = _sha256(data.content)
            doc.version = _bump_version(doc.version) if not data.version else data.version

        await self._commit(doc)
        await self._db.commit()  # 释放 SQLite 写锁（记忆写入走独立连接）
        # 已发布文档内容更新后同步记忆（失败不阻塞）
        if content_updated and doc.status == "published":
            await self._memory_upsert(doc)
        return self._doc_to_dict(doc)

    async def publish_doc(self, doc_id: int, user: dict[str, Any]) -> dict:
        """发布（draft→published）：写记忆 + 事件。"""
        doc = await self._get_editable(doc_id, user)
        if doc.status == "archived":
            raise HTTPException(status_code=400, detail="已归档文档不能发布")
        doc.status = "published"
        doc.published_at = datetime.now(timezone.utc)
        await self._commit(doc)
        await self._db.commit()  # 释放 SQLite 写锁（记忆写入走独立连接）
        await self._memory_upsert(doc)  # 失败不阻塞
        await self._publish_event(
            "docs.portal.published",
            {"doc_id": doc.id, "slug": doc.slug, "version": doc.version, "tenant_id": doc.tenant_id},
        )
        return self._doc_to_dict(doc)

    async def archive_doc(self, doc_id: int, user: dict[str, Any]) -> dict:
        """归档（published→archived）：记忆标记 archived（不删除，历史可追溯）。"""
        doc = await self._get_editable(doc_id, user)
        if doc.status != "published":
            raise HTTPException(status_code=400, detail="仅已发布文档可归档")
        doc.status = "archived"
        await self._commit(doc)
        await self._db.commit()  # 释放 SQLite 写锁（记忆写入走独立连接）
        await self._memory_upsert(doc, archived=True)
        await self._publish_event(
            "docs.portal.archived",
            {"doc_id": doc.id, "slug": doc.slug, "version": doc.version, "tenant_id": doc.tenant_id},
        )
        return self._doc_to_dict(doc)

    # ─── 检索聚合（本地关键词评分） ─────────────────────────────

    async def search_docs(
        self, query: str, top_k: int, user: dict[str, Any]
    ) -> dict:
        """本地关键词检索：限定当前用户可见的 published 文档（title/content 命中加权）。"""
        stmt = self._visible_docs_stmt(user).where(DocItem.status == "published")
        rows = (await self._db.execute(stmt)).scalars().all()
        if not rows:
            await self._publish_event(
                "docs.portal.searched",
                {"query": query[:200], "tenant_id": user.get("tenant_id"), "hits": 0},
            )
            return {"query": query, "answer": "未找到相关文档。", "sources": []}

        tokens = [t for t in re.split(r"\s+", (query or "").strip().lower()) if t]
        scored = []
        for doc in rows:
            haystack = f"{doc.title}\n{doc.summary or ''}\n{doc.content or ''}".lower()
            score = 0
            for tok in tokens:
                count = haystack.count(tok)
                if count:
                    score += count * 10 if tok in doc.title.lower() else count
            if score > 0:
                content = doc.content or ""
                excerpt = content[:200] + ("…" if len(content) > 200 else "")
                scored.append(
                    {
                        "doc_id": str(doc.id),
                        "slug": doc.slug,
                        "version": doc.version,
                        "title": doc.title,
                        "excerpt": excerpt,
                        "score": score,
                        "docs_url": f"/ui/docs.html?id={doc.slug}",
                    }
                )
        scored.sort(key=lambda s: s["score"], reverse=True)
        sources = scored[: max(1, min(int(top_k), 20))]
        await self._publish_event(
            "docs.portal.searched",
            {"query": query[:200], "tenant_id": user.get("tenant_id"), "hits": len(sources)},
        )
        return {"query": query, "answer": "", "sources": sources}

    # ─── 离线部署包（deepDDW 内联内容） ─────────────────────────

    async def export_package(self, user: dict[str, Any]) -> dict:
        """导出发布快照：manifest + 每文档正文（含 content_hash）。"""
        self._assert_admin(user)
        rows = (
            await self._db.execute(
                select(DocItem).where(DocItem.status == "published")
            )
        ).scalars().all()
        docs: list[dict] = []
        for doc in rows:
            content = doc.content or ""
            content_hash = _sha256(content)
            docs.append(
                {
                    "doc_id": doc.id,
                    "slug": doc.slug,
                    "version": doc.version,
                    "title": doc.title,
                    "visibility": doc.visibility,
                    "content_hash": content_hash,
                    "exported_at": _now_iso(),
                    "content": content,
                }
            )
        return {
            "package_version": "1.0",
            "exported_at": _now_iso(),
            "tenant_id": 0,
            "count": len(docs),
            "docs": docs,
        }

    async def import_package(self, data: Any, user: dict[str, Any]) -> dict:
        """导入离线更新包：按 content_hash 去重幂等；导入即 published 并联动记忆。"""
        self._assert_admin(user)
        tenant_id = 0

        imported: list[dict] = []
        skipped: list[dict] = []
        for item in data.docs or []:
            content = item.get("content") or ""
            content_hash = item.get("content_hash") or ""
            slug = item.get("slug") or ""
            title = item.get("title") or slug
            version = item.get("version") or "v1.0"
            visibility = item.get("visibility") or "public"

            if content_hash and _sha256(content) != content_hash:
                skipped.append({"slug": slug, "reason": "content_hash 不匹配（包损坏）"})
                continue
            if content_hash:
                dup = (
                    await self._db.execute(
                        select(DocItem).where(DocItem.content_hash == content_hash)
                    )
                ).scalar_one_or_none()
                if dup is not None:
                    skipped.append({"slug": slug, "reason": "content_hash 已存在（重复导入）"})
                    continue
            if slug:
                slug_dup = (
                    await self._db.execute(
                        select(DocItem).where(
                            DocItem.tenant_id == tenant_id, DocItem.slug == slug
                        )
                    )
                ).scalar_one_or_none()
                if slug_dup is not None:
                    skipped.append({"slug": slug, "reason": "slug 冲突"})
                    continue

            doc = DocItem(
                tenant_id=tenant_id,
                title=title,
                slug=slug,
                doc_type=item.get("doc_type") or "whitepaper",
                visibility=visibility,
                status="published",
                version=version,
                content=content,
                content_hash=content_hash or _sha256(content),
                summary=item.get("summary"),
                author_id=int(user.get("user_id") or 0),
                published_at=datetime.now(timezone.utc),
            )
            self._db.add(doc)
            await self._db.flush()
            await self._db.commit()  # 释放 SQLite 写锁（记忆写入走独立连接）
            await self._memory_upsert(doc)  # 幂等（upsert）
            imported.append(
                {"doc_id": doc.id, "slug": slug, "version": version}
            )

        return {"imported": imported, "skipped": skipped, "count": len(imported)}

    # ─── 序列化 ─────────────────────────────────────────────────

    @staticmethod
    def _category_to_dict(c: DocCategory) -> dict:
        return {
            "id": c.id,
            "parent_id": c.parent_id,
            "name": c.name,
            "slug": c.slug,
            "sort_order": c.sort_order,
            "tenant_id": c.tenant_id,
        }

    @staticmethod
    def _doc_to_dict(d: DocItem) -> dict:
        return {
            "id": d.id,
            "category_id": d.category_id,
            "title": d.title,
            "slug": d.slug,
            "doc_type": d.doc_type,
            "visibility": d.visibility,
            "status": d.status,
            "version": d.version,
            "source_ref": d.source_ref,
            "summary": d.summary,
            "author_id": d.author_id,
            "tenant_id": d.tenant_id,
            "content_hash": d.content_hash,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "updated_at": d.updated_at.isoformat() if d.updated_at else None,
            "published_at": d.published_at.isoformat() if d.published_at else None,
        }
