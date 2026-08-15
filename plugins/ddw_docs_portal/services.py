"""产品文档栏目业务逻辑。

核心设计（对应 PRD 架构决策 1-4）：
- 决策 1 双轨制：tenant_id=0 平台级（public 全租户登录可见）/ tenant_id=N 租户级（本租户）；
  统一 `_visible_docs_stmt()` 过滤，不做跨租户共享表。
- 决策 2 记忆联动：publish 时按 tag `docs_portal:{doc_id}` upsert enterprise 记忆
  （200 字摘要 + docs_url + version），失败不阻塞发布；archive 时标记 archived 不删除。
- 决策 3 检索：search 端点登录鉴权 + 租户过滤；LLM 工具（llm_tool.py）经平台网关链路调用；
  插件层不直连外部 LLM、不存租户 key。
- 决策 4 离线包：export 生成 manifest 快照；import 按 content_hash 去重幂等。

内容存储：正文只存 ddw_doc_assistant（source_ref 引用其 doc_id），portal 不双写内容。
portal 文档在 doc_assistant 向量库统一落 tenant 0 空间，可见性由 docs_item 元数据层过滤
（检索时以可见 source_ref 白名单限定 doc_ids，保证不会命中不可见文档）。
"""
from __future__ import annotations

import hashlib
import logging
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.constants.roles import ADMIN_ROLES
from core.events.bus import get_bus
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

# portal 内容在 doc_assistant 向量库的统一租户空间（可见性由 docs_item 元数据层过滤）
_DA_TENANT = 0
# 平台级文档（tenant_id=0）的记忆挂默认租户（ddw_memory.tenant_id FK tenants.id，0 无对应行）
_MEMORY_FALLBACK_TENANT = 1

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


def _get_memory_service():
    """懒加载 ddw_memory 服务（测试可 monkeypatch）。"""
    from plugins.ddw_memory.service import MemoryService

    return MemoryService()


def _get_da_service(db: AsyncSession):
    """构造 doc_assistant 服务（复用其向量库懒加载单例，支持 set_vector_store_path 注入）。

    llm_chat_fn=None：ingest/检索不需要 LLM 生成，search 走摘录式回答（省 token）。
    """
    from plugins.ddw_doc_assistant.router import _get_vector_store
    from plugins.ddw_doc_assistant.service import DocAssistantService

    return DocAssistantService(
        db=db, vector_store=_get_vector_store(), llm_chat_fn=None
    )


class DocsPortalService:
    """文档栏目核心服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ─── 可见性（决策 1：双轨制统一过滤） ──────────────────────────

    def _visible_docs_stmt(self, user: dict[str, Any]):
        """统一可见文档查询：
        - published +（平台级 public 或 本租户 tenant）→ 任何登录用户
        - draft → 仅作者 + 管理员
        - archived 一律不在可见列表（历史通过版本/DocVersion 追溯）
        """
        tid = int(user.get("tenant_id") or 0)
        uid = int(user.get("user_id") or 0)
        is_admin = (user.get("role") or "member") in ADMIN_ROLES

        published_visible = and_(
            DocItem.status == "published",
            or_(
                and_(DocItem.tenant_id == 0, DocItem.visibility == "public"),
                and_(DocItem.tenant_id == tid, DocItem.visibility == "tenant"),
            ),
        )
        draft_visible = and_(
            DocItem.status == "draft",
            or_(DocItem.author_id == uid, is_admin),
        )
        return select(DocItem).where(or_(published_visible, draft_visible))

    def _assert_admin(self, user: dict[str, Any]) -> None:
        """写操作权限：superadmin/租户管理员。"""
        if (user.get("role") or "member") not in ADMIN_ROLES:
            raise HTTPException(status_code=403, detail="需要管理员权限")

    def _assert_platform_superadmin(self, user: dict[str, Any], tenant_id: int) -> None:
        """平台级资源（tenant_id=0）仅 superadmin 可写。"""
        if tenant_id == 0 and user.get("role") != "superadmin":
            raise HTTPException(status_code=403, detail="平台级文档仅 superadmin 可管理")

    async def _get_editable(self, doc_id: int, user: dict[str, Any]) -> DocItem:
        """可编辑文档：作者或管理员；跨租户 403。"""
        doc = (
            await self._db.execute(select(DocItem).where(DocItem.id == doc_id))
        ).scalar_one_or_none()
        if doc is None:
            raise HTTPException(status_code=404, detail="文档不存在")
        is_admin = (user.get("role") or "member") in ADMIN_ROLES
        if doc.author_id != int(user.get("user_id") or 0) and not is_admin:
            raise HTTPException(status_code=403, detail="仅作者或管理员可编辑该文档")
        return doc

    # ─── doc_assistant 委托 ─────────────────────────────────────

    async def _ingest(self, title: str, content: str) -> str:
        """内容写入 doc_assistant（解析→分块→向量化），返回 doc_id。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        try:
            svc = _get_da_service(self._db)
            meta = await svc.ingest_document(
                tmp_path, title=title, uploader="docs_portal",
                department="docs_portal", tenant_id=_DA_TENANT,
            )
            return str(meta.id)
        finally:
            tmp_path.unlink(missing_ok=True)

    async def _rebuild_content(self, source_ref: str) -> str:
        """从 doc_assistant chunks 重建原文（doc_assistant 不持久化原始文件）。"""
        svc = _get_da_service(self._db)
        chunks = await svc.get_document_chunks(source_ref)
        if not chunks:
            return ""
        # chunks 按 chunk_id 排序返回，按序拼接还原
        return "\n\n".join(c["content"] for c in chunks)

    # ─── 记忆联动（决策 2，M4） ──────────────────────────────────

    def _memory_content(self, doc: DocItem) -> str:
        """enterprise 记忆内容：摘要 + docs_url + version（正文不写记忆，只存 doc_assistant）。"""
        docs_url = f"/ui/docs.html?id={doc.slug}"
        parts = [f"文档：{doc.title}（{doc.version}）", f"链接：{docs_url}"]
        if doc.summary:
            parts.append(f"摘要：{doc.summary}")
        return "\n".join(parts)

    async def _memory_upsert(
        self, doc: DocItem, *, archived: bool = False
    ) -> None:
        """按 tag `docs_portal:{doc_id}` upsert enterprise 记忆；失败不阻塞发布。"""
        try:
            svc = _get_memory_service()
            memory_tenant = doc.tenant_id if doc.tenant_id > 0 else _MEMORY_FALLBACK_TENANT
            tag = f"docs_portal:{doc.id}"

            from plugins.ddw_memory.models import MemoryLayer

            hits = await svc.list_memories(
                tenant_id=memory_tenant, layer=MemoryLayer.ENTERPRISE, page_size=500
            )
            row = next(
                (m for m in hits.get("items", []) if tag in (m.tags or [])), None
            )

            if archived:
                # 归档：标记 archived（不删除，历史可追溯）
                new_tags = (row.tags or []) if row else [tag]
                if "archived" not in new_tags:
                    new_tags = [*new_tags, "archived"]
                if row:
                    await svc.update_memory(memory_tenant, row.id, tags=new_tags)
                return

            content = self._memory_content(doc)
            if row:
                # 同文档更新 = 更新同一条记忆（决策 2：upsert，不新增）
                tags = [t for t in (row.tags or []) if t != "archived"] or [tag]
                await svc.update_memory(memory_tenant, row.id, content=content, tags=tags)
                logger.info("docs_portal: enterprise memory updated doc=%s", doc.id)
            else:
                await svc.create_memory(
                    tenant_id=memory_tenant,
                    layer=MemoryLayer.ENTERPRISE,
                    content=content,
                    creator_id=doc.author_id or 0,
                    tags=[tag],
                    source_type="docs_portal",
                )
                logger.info("docs_portal: enterprise memory created doc=%s", doc.id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("docs_portal: memory upsert failed for doc %s: %s", doc.id, exc)

    async def _publish_event(self, event: str, payload: dict[str, Any]) -> None:
        try:
            await get_bus().publish(event, payload, source=PLUGIN_NAME)
        except Exception as exc:  # noqa: BLE001
            logger.warning("docs_portal: event %s publish failed: %s", event, exc)

    async def _commit(self, obj) -> None:
        """flush + refresh：回填 server_default（created_at/updated_at）后再序列化。"""
        await self._db.flush()
        await self._db.refresh(obj)

    # ─── 目录树 ─────────────────────────────────────────────────

    async def list_categories_tree(self, user: dict[str, Any]) -> list[dict]:
        """目录树（平台级 0 + 本租户）。"""
        tid = int(user.get("tenant_id") or 0)
        rows = (
            await self._db.execute(
                select(DocCategory)
                .where(DocCategory.tenant_id.in_([0, tid]))
                .order_by(DocCategory.sort_order.asc(), DocCategory.id.asc())
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
        """建分类（superadmin 建平台级 0；租户管理员建本租户）。"""
        self._assert_admin(user)
        tenant_id = 0 if user.get("role") == "superadmin" else int(user.get("tenant_id") or 0)
        self._assert_platform_superadmin(user, tenant_id)
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
        """改分类（同名权限）。"""
        self._assert_admin(user)
        cat = (
            await self._db.execute(select(DocCategory).where(DocCategory.id == category_id))
        ).scalar_one_or_none()
        if cat is None:
            raise HTTPException(status_code=404, detail="分类不存在")
        self._assert_platform_superadmin(user, cat.tenant_id)
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
        """文档列表（目录/类型/可见性过滤，只返回当前用户可见文档）。"""
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
        """文档详情：元数据 + 从 doc_assistant 重建的正文。"""
        tid = int(user.get("tenant_id") or 0)
        uid = int(user.get("user_id") or 0)
        is_admin = (user.get("role") or "member") in ADMIN_ROLES

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
            elif raw.visibility == "tenant" and raw.tenant_id != tid:
                raise HTTPException(status_code=403, detail="该文档仅本租户可见")
            elif raw.status == "draft" and raw.author_id != uid and not is_admin:
                raise HTTPException(status_code=403, detail="该文档为草稿，仅作者或管理员可见")
            else:
                raise HTTPException(status_code=404, detail="文档不存在")

        result = self._doc_to_dict(doc)
        result["content"] = await self._rebuild_content(doc.source_ref)
        return result

    async def create_doc(self, data: Any, user: dict[str, Any]) -> dict:
        """新建文档：内容写入 doc_assistant ingest，元数据存 docs_item。"""
        self._assert_admin(user)
        tenant_id = 0 if user.get("role") == "superadmin" else int(user.get("tenant_id") or 0)
        self._assert_platform_superadmin(user, tenant_id)
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

        source_ref = await self._ingest(data.title, data.content)
        doc = DocItem(
            tenant_id=tenant_id,
            category_id=data.category_id,
            title=data.title,
            slug=data.slug,
            doc_type=data.doc_type,
            visibility=data.visibility,
            status="draft",
            version=data.version or "v1.0",
            source_ref=source_ref,
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
        """更新：重新 ingest（新 doc_id）→ 旧 source_ref 入 DocVersion → version 递增。"""
        doc = await self._get_editable(doc_id, user)
        self._assert_platform_superadmin(user, doc.tenant_id)

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
            # 重新 ingest：旧内容进版本历史
            old_ref = doc.source_ref
            new_ref = await self._ingest(doc.title, data.content)
            self._db.add(
                DocVersion(
                    tenant_id=doc.tenant_id,
                    doc_id=doc.id,
                    version=doc.version,
                    change_note=data.version or "内容更新",
                    source_ref=old_ref,
                )
            )
            doc.source_ref = new_ref
            doc.content_hash = _sha256(data.content)
            doc.version = _bump_version(doc.version) if not data.version else data.version

        await self._commit(doc)
        await self._db.commit()  # 释放 SQLite 写锁（memory 写入走独立连接）
        # 已发布文档内容更新后同步 enterprise 记忆（决策 2：失败不阻塞）
        if content_updated and doc.status == "published":
            await self._memory_upsert(doc)
        return self._doc_to_dict(doc)

    async def publish_doc(self, doc_id: int, user: dict[str, Any]) -> dict:
        """发布（draft→published）：写 enterprise 记忆（按 doc_id upsert）+ 事件。"""
        doc = await self._get_editable(doc_id, user)
        self._assert_platform_superadmin(user, doc.tenant_id)
        if doc.status == "archived":
            raise HTTPException(status_code=400, detail="已归档文档不能发布")
        doc.status = "published"
        doc.published_at = datetime.now(timezone.utc)
        await self._commit(doc)
        await self._db.commit()  # 释放 SQLite 写锁（memory 写入走独立连接）
        await self._memory_upsert(doc)  # 决策 2：失败不阻塞
        await self._publish_event(
            "docs.portal.published",
            {"doc_id": doc.id, "slug": doc.slug, "version": doc.version, "tenant_id": doc.tenant_id},
        )
        return self._doc_to_dict(doc)

    async def archive_doc(self, doc_id: int, user: dict[str, Any]) -> dict:
        """归档（published→archived）：记忆标记 archived（不删除，历史可追溯）。"""
        doc = await self._get_editable(doc_id, user)
        self._assert_platform_superadmin(user, doc.tenant_id)
        if doc.status != "published":
            raise HTTPException(status_code=400, detail="仅已发布文档可归档")
        doc.status = "archived"
        await self._commit(doc)
        await self._db.commit()  # 释放 SQLite 写锁（memory 写入走独立连接）
        await self._memory_upsert(doc, archived=True)
        await self._publish_event(
            "docs.portal.archived",
            {"doc_id": doc.id, "slug": doc.slug, "version": doc.version, "tenant_id": doc.tenant_id},
        )
        return self._doc_to_dict(doc)

    # ─── 检索聚合（决策 3 统一入口） ─────────────────────────────

    async def search_docs(
        self, query: str, top_k: int, user: dict[str, Any]
    ) -> dict:
        """混合检索：限定当前用户可见的 published 文档（source_ref 白名单）。"""
        stmt = self._visible_docs_stmt(user).where(DocItem.status == "published")
        rows = (await self._db.execute(stmt)).scalars().all()
        ref2doc = {d.source_ref: d for d in rows if d.source_ref}
        if not ref2doc:
            await self._publish_event(
                "docs.portal.searched",
                {"query": query[:200], "tenant_id": user.get("tenant_id"), "hits": 0},
            )
            return {"query": query, "answer": "未找到相关文档。", "sources": []}

        svc = _get_da_service(self._db)
        result = await svc.query(
            query, doc_ids=list(ref2doc.keys()), top_k=top_k, tenant_id=_DA_TENANT
        )
        sources = []
        for s in result.get("sources", []):
            doc = ref2doc.get(s.get("doc_id", ""))
            sources.append(
                {
                    **s,
                    "slug": doc.slug if doc else "",
                    "version": doc.version if doc else "",
                    "docs_url": f"/ui/docs.html?id={doc.slug}" if doc else "",
                }
            )
        await self._publish_event(
            "docs.portal.searched",
            {"query": query[:200], "tenant_id": user.get("tenant_id"), "hits": len(sources)},
        )
        return {"query": query, "answer": result.get("answer", ""), "sources": sources}

    # ─── 离线部署包（决策 4，M5） ───────────────────────────────

    async def export_package(self, user: dict[str, Any]) -> dict:
        """导出发布快照：manifest + 每文档重建正文（含 content_hash）。"""
        self._assert_admin(user)
        rows = (
            await self._db.execute(
                select(DocItem).where(DocItem.status == "published")
            )
        ).scalars().all()
        docs: list[dict] = []
        for doc in rows:
            content = await self._rebuild_content(doc.source_ref)
            content_hash = _sha256(content)
            doc.content_hash = content_hash  # 与导出包保持一致（幂等导入基准）
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
        await self._db.flush()
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
        tenant_id = int(getattr(data, "tenant_id", 0) or 0)
        if (
            tenant_id != 0
            and user.get("role") != "superadmin"
            and int(user.get("tenant_id") or 0) != tenant_id
        ):
            # 租户制度包：仅该租户管理员或 superadmin 可导入
            raise HTTPException(status_code=403, detail="无权导入该租户文档包")

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

            source_ref = await self._ingest(title, content)
            doc = DocItem(
                tenant_id=tenant_id,
                title=title,
                slug=slug,
                doc_type=item.get("doc_type") or "whitepaper",
                visibility=visibility,
                status="published",
                version=version,
                source_ref=source_ref,
                content_hash=content_hash or _sha256(content),
                summary=item.get("summary"),
                author_id=int(user.get("user_id") or 0),
                published_at=datetime.now(timezone.utc),
            )
            self._db.add(doc)
            await self._db.flush()
            await self._db.commit()  # 释放 SQLite 写锁（memory 写入走独立连接）
            await self._memory_upsert(doc)  # 幂等（upsert），FDE 导入后记忆完整
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
