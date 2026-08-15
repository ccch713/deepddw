"""产品文档栏目 12 条测试（TASK_SPEC 第七节；mock 依赖，不碰真实服务）。"""
from __future__ import annotations

import pytest
from core.database.tenant_filter import bypass_tenant_filter
from fastapi import HTTPException
from sqlalchemy import select

from plugins.ddw_docs_portal import models as M
from plugins.ddw_docs_portal.kb_bridge import build_kb_bridge, default_public_search
from plugins.ddw_docs_portal.llm_tool import TOOL_NAME, docs_search_tool_definition
from plugins.ddw_docs_portal.models import (
    CategoryCreateReq,
    DocCreateReq,
    DocUpdateReq,
    ImportPackageReq,
)
from plugins.ddw_docs_portal.services import DocsPortalService

from .conftest import MEMBER_A, MEMBER_B, SUPERADMIN, TENANT_ADMIN

API = "/api/v1/plugins/ddw-docs-portal"


def _cat(name: str, slug: str, parent_id=None) -> CategoryCreateReq:
    return CategoryCreateReq(name=name, slug=slug, parent_id=parent_id, sort_order=0)


def _doc(title: str, slug: str, content: str, visibility: str = "public", **kw) -> DocCreateReq:
    return DocCreateReq(
        title=title,
        slug=slug,
        content=content,
        visibility=visibility,
        doc_type=kw.pop("doc_type", "whitepaper"),
        summary=kw.pop("summary", "测试摘要"),
        **kw,
    )


async def _create_published(
    service: DocsPortalService,
    user: dict,
    title: str,
    slug: str,
    content: str = "DDW 平台部署说明",
    visibility: str = "public",
) -> dict:
    doc = await service.create_doc(_doc(title, slug, content, visibility), user)
    await service.publish_doc(doc["id"], user)
    return doc


# ─── 1. 建父子分类 → 目录树结构正确 ────────────────────────────


@pytest.mark.asyncio
async def test_01_category_tree(service):
    async with bypass_tenant_filter():
        root = await service.create_category(_cat("产品资料", "products"), SUPERADMIN)
        await service.create_category(
            _cat("白皮书", "whitepapers", parent_id=root["id"]), SUPERADMIN
        )
        tree = await service.list_categories_tree(MEMBER_A)
    assert len(tree) == 1
    assert tree[0]["slug"] == "products"
    assert tree[0]["children"][0]["slug"] == "whitepapers"


# ─── 2. 发布 public 文档 → 列表全租户可见 ───────────────────────


@pytest.mark.asyncio
async def test_02_public_doc_visible_across_tenants(service):
    async with bypass_tenant_filter():
        await _create_published(service, SUPERADMIN, "DDW 白皮书", "whitepaper-v1")
        items_a = await service.list_docs(MEMBER_A)
        items_b = await service.list_docs(MEMBER_B)
    slugs_a = {d["slug"] for d in items_a["items"]}
    slugs_b = {d["slug"] for d in items_b["items"]}
    assert "whitepaper-v1" in slugs_a
    assert "whitepaper-v1" in slugs_b


# ─── 3. 发布 tenant 文档 → 本租户可见，跨租户 403 ───────────────


@pytest.mark.asyncio
async def test_03_tenant_doc_forbidden_across_tenants(service):
    async with bypass_tenant_filter():
        await _create_published(
            service, TENANT_ADMIN, "客户制度", "customer-regulation", visibility="tenant"
        )
        items_a = await service.list_docs(MEMBER_A)
        items_b = await service.list_docs(MEMBER_B)
        doc_id = items_a["items"][0]["id"]
        assert items_a["total"] == 1
        assert items_b["total"] == 0
        with pytest.raises(HTTPException) as exc:
            await service.get_doc(doc_id, MEMBER_B)
        assert exc.value.status_code == 403


# ─── 4. 未登录访问文档 → 401（白皮书红线） ──────────────────────


@pytest.mark.asyncio
async def test_04_unauthenticated_401(client):
    resp = await client.get(f"{API}/docs")
    assert resp.status_code == 401
    resp2 = await client.get(f"{API}/search", params={"q": "部署"})
    assert resp2.status_code == 401


# ─── 5. 更新文档 → version 递增 + DocVersion 记录 ──────────────


@pytest.mark.asyncio
async def test_05_update_bumps_version_and_keeps_history(service, fake_da):
    async with bypass_tenant_filter():
        doc = await service.create_doc(
            _doc("部署手册", "deploy-guide", "旧内容 v1"), SUPERADMIN
        )
        old_ref = doc["source_ref"]
        updated = await service.update_doc(
            doc["id"], DocUpdateReq(content="新内容 v2"), SUPERADMIN
        )
        versions = (
            await service._db.execute(
                select(M.DocVersion).where(M.DocVersion.doc_id == doc["id"])
            )
        ).scalars().all()
    assert updated["version"] == "v1.1"
    assert updated["source_ref"] != old_ref
    assert len(versions) == 1
    assert versions[0].source_ref == old_ref


# ─── 6. publish → enterprise 记忆 upsert（同 doc 两次 publish 只一条） ──


@pytest.mark.asyncio
async def test_06_publish_memory_upsert(service, fake_da, fake_memory):
    async with bypass_tenant_filter():
        doc = await service.create_doc(
            _doc("退款规则", "refund-policy", "退款规则内容", summary="≤200 字摘要"),
            SUPERADMIN,
        )
        await service.publish_doc(doc["id"], SUPERADMIN)
        assert fake_memory.created == 1
        assert fake_memory.updated == 0

        # 更新已发布文档 → 记忆同步更新（仍一条）
        await service.update_doc(
            doc["id"], DocUpdateReq(content="退款规则 v2 内容"), SUPERADMIN
        )
        assert fake_memory.created == 1
        assert fake_memory.updated == 1

        # 再次 publish（幂等）→ 仍然只有一条记忆
        await service.publish_doc(doc["id"], SUPERADMIN)
        assert fake_memory.created == 1
        assert fake_memory.updated == 2
        assert len(fake_memory.items) == 1
        assert f"docs_portal:{doc['id']}" in fake_memory.items[0].tags
        assert "docs_url" in fake_memory.items[0].content or "/ui/docs.html" in fake_memory.items[0].content


# ─── 7. search → 命中 published 文档（mock doc_assistant） ──────


@pytest.mark.asyncio
async def test_07_search_hits_published(service, fake_da):
    async with bypass_tenant_filter():
        await _create_published(service, SUPERADMIN, "DDW 白皮书", "whitepaper-v1")
        result = await service.search_docs("DDW 怎么接 ERP", 5, MEMBER_A)
    assert result["sources"]
    assert result["sources"][0]["slug"] == "whitepaper-v1"
    assert result["sources"][0]["docs_url"].startswith("/ui/docs.html?id=")


# ─── 8. 归档 → 列表不可见，但版本可查 ───────────────────────────


@pytest.mark.asyncio
async def test_08_archive_hides_from_list_but_version_accessible(service):
    async with bypass_tenant_filter():
        doc = await _create_published(service, SUPERADMIN, "旧制度", "old-regulation")
        await service.archive_doc(doc["id"], SUPERADMIN)

        items = await service.list_docs(MEMBER_A)
        assert "old-regulation" not in {d["slug"] for d in items["items"]}

        # 作者/管理员仍可查（归档语义：历史可追溯）
        detail = await service.get_doc(doc["id"], SUPERADMIN)
        assert detail["status"] == "archived"

        # 普通成员不可见
        with pytest.raises(HTTPException) as exc:
            await service.get_doc(doc["id"], MEMBER_A)
        assert exc.value.status_code == 404


# ─── 9. export → manifest 字段齐全 ──────────────────────────────


@pytest.mark.asyncio
async def test_09_export_manifest(service, fake_da):
    async with bypass_tenant_filter():
        await _create_published(service, SUPERADMIN, "白皮书", "wp-1")
        await _create_published(service, SUPERADMIN, "手册", "manual-1")
        pkg = await service.export_package(SUPERADMIN)
    assert pkg["count"] == 2
    assert pkg["package_version"] == "1.0"
    for d in pkg["docs"]:
        assert {"doc_id", "slug", "version", "content_hash", "exported_at"} <= set(d)
        assert d["content_hash"]  # 非空


# ─── 10. import → 重复导入幂等（同 content_hash 跳过） ──────────


@pytest.mark.asyncio
async def test_10_import_idempotent(service, fake_da):
    content = "# 部署指南\n部署需要 3 天。"
    import hashlib

    payload = [
        {
            "doc_id": 1,
            "slug": "deploy-guide",
            "version": "v1.0",
            "title": "部署指南",
            "visibility": "public",
            "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "exported_at": "2026-08-14T00:00:00+00:00",
            "content": content,
        }
    ]
    async with bypass_tenant_filter():
        r1 = await service.import_package(ImportPackageReq(docs=payload), SUPERADMIN)
        r2 = await service.import_package(ImportPackageReq(docs=payload), SUPERADMIN)
    assert len(r1["imported"]) == 1
    assert len(r2["imported"]) == 0
    assert r2["skipped"][0]["reason"] == "content_hash 已存在（重复导入）"
    assert fake_da.ingested == 1  # 只 ingest 一次


# ─── 11. llm_tool → docs_search 工具符合 function calling 格式 ──


def test_11_llm_tool_function_calling_format():
    defn = docs_search_tool_definition()
    assert defn["type"] == "function"
    fn = defn["function"]
    assert fn["name"] == TOOL_NAME == "ddw.docs_portal.search"
    assert fn["parameters"]["type"] == "object"
    assert fn["parameters"]["required"] == ["query"]
    assert "query" in fn["parameters"]["properties"]


# ─── 12. kb_bridge → 客服检索并入 docs 结果且按租户过滤 ─────────


@pytest.mark.asyncio
async def test_12_kb_bridge_merges_docs_and_filters_by_visibility(service, fake_da):
    # 桥接结构：注入 fake 检索函数
    async def fake_portal_search(query, top_k):
        return [{"content": "部署要多久：3 天", "slug": "deploy-guide", "score": 0.9}]

    bridge = build_kb_bridge(fake_portal_search)
    results = await bridge.search("部署要多久", 4)
    assert results[0]["source"] == "docs:deploy-guide"
    assert results[0]["content"] == "部署要多久：3 天"

    # 默认实现（客服无租户身份）只返回平台级 public，不泄漏 tenant 文档
    async with bypass_tenant_filter():
        await _create_published(service, SUPERADMIN, "公开白皮书", "pub-wp")
        await _create_published(
            service, TENANT_ADMIN, "租户制度", "tenant-secret", visibility="tenant"
        )
        public_results = await default_public_search("内容", 5)
    slugs = {r["slug"] for r in public_results}
    assert "pub-wp" in slugs
    assert "tenant-secret" not in slugs
