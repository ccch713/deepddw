"""产品文档栏目测试（deepDDW 开源裁剪版；mock 外部依赖，不碰真实服务）。"""
from __future__ import annotations

import hashlib

import pytest
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

from .conftest import MEMBER_A, SUPERADMIN

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
    root = await service.create_category(_cat("产品资料", "products"), SUPERADMIN)
    await service.create_category(
        _cat("白皮书", "whitepapers", parent_id=root["id"]), SUPERADMIN
    )
    tree = await service.list_categories_tree(MEMBER_A)
    assert len(tree) == 1
    assert tree[0]["slug"] == "products"
    assert tree[0]["children"][0]["slug"] == "whitepapers"


# ─── 2. 发布 public 文档 → 列表可见 ─────────────────────────────


@pytest.mark.asyncio
async def test_02_public_doc_visible(service):
    await _create_published(service, SUPERADMIN, "DDW 白皮书", "whitepaper-v1")
    items_a = await service.list_docs(MEMBER_A)
    slugs_a = {d["slug"] for d in items_a["items"]}
    assert "whitepaper-v1" in slugs_a


# ─── 3. 非 public 可见性 → member 不可见，管理员可见 ────────────


@pytest.mark.asyncio
async def test_03_tenant_doc_forbidden_for_member(service):
    await _create_published(
        service, SUPERADMIN, "客户制度", "customer-regulation", visibility="tenant"
    )
    items_a = await service.list_docs(MEMBER_A)
    assert items_a["total"] == 0
    # 管理员（token 持有者）可见已发布 tenant 文档
    items_admin = await service.list_docs(SUPERADMIN)
    assert items_admin["total"] == 1


# ─── 4. 未带 Token 访问文档 → 401（P0-1 门禁） ──────────────────


@pytest.mark.asyncio
async def test_04_unauthenticated_401(client):
    resp = await client.get(f"{API}/docs")
    assert resp.status_code == 401
    resp2 = await client.get(f"{API}/search", params={"q": "部署"})
    assert resp2.status_code == 401


# ─── 5. 更新文档 → version 递增 + DocVersion 记录 ──────────────


@pytest.mark.asyncio
async def test_05_update_bumps_version_and_keeps_history(service):
    doc = await service.create_doc(
        _doc("部署手册", "deploy-guide", "旧内容 v1"), SUPERADMIN
    )
    updated = await service.update_doc(
        doc["id"], DocUpdateReq(content="新内容 v2"), SUPERADMIN
    )
    versions = (
        await service._db.execute(
            select(M.DocVersion).where(M.DocVersion.doc_id == doc["id"])
        )
    ).scalars().all()
    assert updated["version"] == "v1.1"
    assert updated["content_hash"] == hashlib.sha256("新内容 v2".encode("utf-8")).hexdigest()
    assert len(versions) == 1
    assert versions[0].source_ref == hashlib.sha256("旧内容 v1".encode("utf-8")).hexdigest()


# ─── 6. publish → deepDDW 记忆 upsert（同 doc 多次 publish 只一条） ──


@pytest.mark.asyncio
async def test_06_publish_memory_upsert(service):
    from core.knowledge import memory_get

    doc = await service.create_doc(
        _doc("退款规则", "refund-policy", "退款规则内容", summary="≤200 字摘要"),
        SUPERADMIN,
    )
    await service.publish_doc(doc["id"], SUPERADMIN)
    mem = memory_get("docs_portal", f"doc:{doc['id']}")
    assert mem["found"] is True
    assert "/ui/docs.html" in mem["value"]

    # 更新已发布文档 → 记忆同步更新（仍一条）
    await service.update_doc(
        doc["id"], DocUpdateReq(content="退款规则 v2 内容"), SUPERADMIN
    )
    mem2 = memory_get("docs_portal", f"doc:{doc['id']}")
    assert mem2["found"] is True

    # 再次 publish（幂等）→ 仍然只有一条记忆
    await service.publish_doc(doc["id"], SUPERADMIN)
    mem3 = memory_get("docs_portal", f"doc:{doc['id']}")
    assert mem3["found"] is True


# ─── 7. search → 命中 published 文档（本地关键词检索） ──────────


@pytest.mark.asyncio
async def test_07_search_hits_published(service):
    await _create_published(service, SUPERADMIN, "DDW 白皮书", "whitepaper-v1")
    result = await service.search_docs("DDW 平台", 5, MEMBER_A)
    assert result["sources"]
    assert result["sources"][0]["slug"] == "whitepaper-v1"
    assert result["sources"][0]["docs_url"].startswith("/ui/docs.html?id=")


# ─── 8. 归档 → 列表不可见，但版本可查 ───────────────────────────


@pytest.mark.asyncio
async def test_08_archive_hides_from_list_but_version_accessible(service):
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
async def test_09_export_manifest(service):
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
async def test_10_import_idempotent(service):
    content = "# 部署指南\n部署需要 3 天。"
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
    r1 = await service.import_package(ImportPackageReq(docs=payload), SUPERADMIN)
    r2 = await service.import_package(ImportPackageReq(docs=payload), SUPERADMIN)
    assert len(r1["imported"]) == 1
    assert len(r2["imported"]) == 0
    assert r2["skipped"][0]["reason"] == "content_hash 已存在（重复导入）"
    # 内容内联存储（不再委托 doc_assistant）
    detail = await service.get_doc(r1["imported"][0]["doc_id"], SUPERADMIN)
    assert detail["content"] == content


# ─── 11. llm_tool → docs_search 工具符合 function calling 格式 ──


def test_11_llm_tool_function_calling_format():
    defn = docs_search_tool_definition()
    assert defn["type"] == "function"
    fn = defn["function"]
    assert fn["name"] == TOOL_NAME == "ddw.docs_portal.search"
    assert fn["parameters"]["type"] == "object"
    assert fn["parameters"]["required"] == ["query"]
    assert "query" in fn["parameters"]["properties"]


# ─── 12. kb_bridge → 检索并入 docs 结果且按可见性过滤 ───────────


@pytest.mark.asyncio
async def test_12_kb_bridge_merges_docs_and_filters_by_visibility(service):
    # 桥接结构：注入 fake 检索函数
    async def fake_portal_search(query, top_k):
        return [{"excerpt": "部署要多久：3 天", "slug": "deploy-guide", "score": 0.9}]

    bridge = build_kb_bridge(fake_portal_search)
    results = await bridge.search("部署要多久", 4)
    assert results[0]["source"] == "docs:deploy-guide"
    assert results[0]["content"] == "部署要多久：3 天"

    # 默认实现（无身份场景）只返回 public，不泄漏 tenant 文档
    await _create_published(service, SUPERADMIN, "公开白皮书", "pub-wp")
    await _create_published(
        service, SUPERADMIN, "租户制度", "tenant-secret", visibility="tenant"
    )
    public_results = await default_public_search("部署", 5)
    slugs = {r["slug"] for r in public_results}
    assert "pub-wp" in slugs
    assert "tenant-secret" not in slugs
