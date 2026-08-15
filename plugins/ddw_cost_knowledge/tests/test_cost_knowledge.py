"""ddw_cost_knowledge 单元 + 集成测试。"""

from __future__ import annotations


import pytest

from plugins.ddw_cost_knowledge.models import CostDocument
from plugins.ddw_cost_knowledge.services.search_service import SearchService

# ---------------------------------------------------------------------------
# 单元：SearchService 分词
# ---------------------------------------------------------------------------


def test_tokenize_mixed():
    s = SearchService()
    toks = s._tokenize("武汉 住宅 框架结构 3500 元")
    # 包含英文/数字
    assert "3500" in toks
    assert "武汉" in toks or "武汉" in "".join(toks)
    # 中文 bigram
    assert "武汉" in "".join(toks) or any(t == "武汉" for t in toks)


def test_score_match():

    s = SearchService()
    d = CostDocument(
        tenant_id=1, file_name="光谷A住宅造价.pdf", doc_type="历史造价文件",
        project_name="光谷A住宅项目", project_type="住宅",
        area=50000.0, total_cost=175000000.0, status="processed",
    )
    score, snippet = s._score(d, s._tokenize("住宅 光谷"))
    assert score > 0
    assert "住宅" in snippet or "光谷" in snippet


def test_score_no_match():

    s = SearchService()
    d = CostDocument(
        tenant_id=1, file_name="x.pdf", doc_type="历史造价文件", status="processed",
    )
    score, _ = s._score(d, ["完全不相关", "关键词"])
    assert score == 0


# ---------------------------------------------------------------------------
# 集成：上传 / 列表 / 删除
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_metadata_only(db_session, import_service, seeded_tenant):
    doc = await import_service.upload(db_session, {
        "tenant_id": seeded_tenant,
        "file_name": "测试项目.pdf",
        "doc_type": "历史造价文件",
        "project_name": "测试项目",
        "project_type": "住宅",
        "area": 10000.0,
        "total_cost": 30000000.0,
    })
    await db_session.commit()
    assert doc.id is not None
    assert doc.status == "pending"
    # 列表
    total, items = await import_service.list(db_session)
    assert total == 1
    # 按 project_type 过滤
    total2, _ = await import_service.list(db_session, project_type="商业")
    assert total2 == 0


@pytest.mark.asyncio
async def test_upload_with_binary(db_session, import_service, seeded_tenant, tmp_path):
    import base64

    content = b"fake pdf content for test"
    payload = {
        "tenant_id": seeded_tenant,
        "file_name": "实测文件.pdf",
        "doc_type": "历史造价文件",
        "file_content_b64": base64.b64encode(content).decode(),
        "project_name": "测试",
    }
    doc = await import_service.upload(db_session, payload)
    await db_session.commit()
    assert doc.file_path is not None
    # 文件真的写到了磁盘
    import os

    assert os.path.exists(doc.file_path)
    with open(doc.file_path, "rb") as f:
        assert f.read() == content


@pytest.mark.asyncio
async def test_delete_removes_file(db_session, import_service, seeded_tenant, tmp_path):
    import base64
    import os
    payload = {
        "tenant_id": seeded_tenant,
        "file_name": "del.pdf",
        "file_content_b64": base64.b64encode(b"x").decode(),
    }
    doc = await import_service.upload(db_session, payload)
    await db_session.commit()
    fp = doc.file_path
    assert fp and os.path.exists(fp)
    ok = await import_service.delete(db_session, doc.id)
    await db_session.commit()
    assert ok is True
    assert not os.path.exists(fp)


# ---------------------------------------------------------------------------
# 集成：提炼
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_rule_based(db_session, import_service, extract_service, seeded_tenant):
    doc = await import_service.upload(db_session, {
        "tenant_id": seeded_tenant, "file_name": "光谷项目.pdf",
        "doc_type": "历史造价文件", "project_name": "光谷住宅A",
        "project_type": "住宅", "area": 30000.0, "total_cost": 90000000.0,
    })
    await db_session.commit()

    data = await extract_service.extract(db_session, doc, use_llm=False)
    await db_session.commit()

    assert data["scale"] in ("small", "medium", "large")
    assert "unit_price" in data
    # 单方 = 90000000 / 30000 = 3000
    assert abs(data["unit_price"] - 3000.0) < 0.01
    assert data["cost_tier"] in ("low", "medium", "high", "premium")
    assert doc.status == "processed"
    assert doc.extracted_data is not None


# ---------------------------------------------------------------------------
# 集成：估算
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_estimate_with_no_refs(db_session, estimate_service, seeded_tenant):
    est = await estimate_service.create(db_session, {
        "tenant_id": seeded_tenant,
        "project_name": "无参考估算",
        "project_type": "住宅",
        "area": 10000.0,
        "floor_count": 10,
        "structure_type": "框架",
    })
    await db_session.commit()
    assert est.id is not None
    assert est.confidence == 0.0
    assert est.estimate_result["method"] == "fallback"


@pytest.mark.asyncio
async def test_estimate_with_refs(db_session, import_service, extract_service, estimate_service, seeded_tenant):
    # 准备 3 个历史项目
    refs = [
        ("项目A", "住宅", 20000.0, 60000000.0),  # 单方 3000
        ("项目B", "住宅", 30000.0, 96000000.0),  # 单方 3200
        ("项目C", "住宅", 40000.0, 140000000.0),  # 单方 3500
    ]
    for n, pt, a, tc in refs:
        d = await import_service.upload(db_session, {
            "tenant_id": seeded_tenant, "file_name": f"{n}.pdf",
            "doc_type": "历史造价文件", "project_name": n,
            "project_type": pt, "area": a, "total_cost": tc,
        })
        await extract_service.extract(db_session, d)
    await db_session.commit()

    est = await estimate_service.create(db_session, {
        "tenant_id": seeded_tenant,
        "project_name": "新项目估算",
        "project_type": "住宅",
        "area": 25000.0,
        "floor_count": 15,
        "structure_type": "框剪",  # 修正系数 1.05
    })
    await db_session.commit()

    assert est.confidence > 0.3
    assert est.estimate_result["method"] == "weighted_median"
    assert est.estimate_result["samples"] == 3
    # 中位数 3200，q1 3000，q3 3500 → blended ≈ 0.4*3200 + 0.3*3000 + 0.3*3500 = 3230
    # 框剪 1.05 → 3391.5
    up = est.estimate_result["unit_price"]
    assert 3300 < up < 3450
    assert abs(est.estimate_result["total_cost"] - up * 25000) < 1
    assert est.reference_docs is not None
    assert len(est.reference_docs) == 3


# ---------------------------------------------------------------------------
# 集成：检索
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_basic(db_session, import_service, search_service, seeded_tenant):
    docs = [
        ("光谷住宅A.pdf", "光谷住宅项目A", "住宅", 50000, 150000000),
        ("光谷住宅B.pdf", "光谷住宅项目B", "住宅", 60000, 195000000),
        ("江汉商业.pdf", "江汉商业中心", "商业", 30000, 180000000),
    ]
    for fn, pn, pt, a, tc in docs:
        await import_service.upload(db_session, {
            "tenant_id": seeded_tenant, "file_name": fn,
            "doc_type": "历史造价文件", "project_name": pn,
            "project_type": pt, "area": a, "total_cost": tc,
        })
    await db_session.commit()

    # 搜 "光谷 住宅"
    hits = await search_service.search(db_session, "光谷 住宅")
    assert len(hits) == 2
    assert all("光谷" in h["file_name"] or "光谷" in (h["project_name"] or "") for h in hits)

    # 搜 "商业" 加 project_type 过滤
    hits2 = await search_service.search(db_session, "商业", project_type="商业")
    assert len(hits2) == 1
    assert hits2[0]["file_name"] == "江汉商业.pdf"

    # 无结果
    hits3 = await search_service.search(db_session, "不存在的关键词xyz")
    assert len(hits3) == 0


# ---------------------------------------------------------------------------
# 集成：批量导入
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_import(db_session, import_service, seeded_tenant):
    items = [
        {"file_name": "x1.pdf", "doc_type": "定额", "project_name": "X1", "project_type": "住宅"},
        {"file_name": "x2.pdf", "doc_type": "清单", "project_name": "X2", "project_type": "商业"},
    ]
    result = await import_service.batch_import(db_session, items, tenant_id=seeded_tenant)
    await db_session.commit()
    assert result["success"] == 2
    assert result["failed"] == 0
    assert len(result["document_ids"]) == 2
    total, _ = await import_service.list(db_session)
    assert total == 2


# ---------------------------------------------------------------------------
# Router 路径检查
# ---------------------------------------------------------------------------


def test_router_has_10_endpoints():
    from plugins.ddw_cost_knowledge.router import build_router

    class P:
        name = "ddw-cost-knowledge"
        import_service = type("S", (), {})()
        extract_service = type("S", (), {})()
        estimate_service = type("S", (), {})()
        search_service = type("S", (), {})()

    r = build_router(P())
    collected = {}
    for route in r.routes:
        if not hasattr(route, "methods"):
            continue
        # 跳过 UI 页面路由（不进 OpenAPI 的 include_in_schema=False 路由）
        if getattr(route, "include_in_schema", True) is False:
            continue
        for m in route.methods:
            collected.setdefault(route.path, set()).add(m)

    total = sum(len(s) for s in collected.values())
    assert total == 11, f"expected 11 endpoints, got {total}: {collected}"

    prefix = "/api/v1/plugins/ddw-cost-knowledge"
    expected = [
        (f"{prefix}/documents/upload", "POST"),
        (f"{prefix}/documents", "GET"),
        (f"{prefix}/documents/{{doc_id}}", "GET"),
        (f"{prefix}/documents/{{doc_id}}", "DELETE"),
        (f"{prefix}/documents/{{doc_id}}/extract", "POST"),
        (f"{prefix}/search", "GET"),
        (f"{prefix}/estimates", "POST"),
        (f"{prefix}/estimates/{{est_id}}", "GET"),
        (f"{prefix}/stats", "GET"),
        (f"{prefix}/batch-import", "POST"),
    ]
    for path, method in expected:
        assert path in collected, f"missing path: {path}"
        assert method in collected[path], f"missing method {method} on {path}"
