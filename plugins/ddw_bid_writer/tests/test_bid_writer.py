"""ddw_bid_writer 单元 + 集成测试。

特别关注：脱敏要求 — UI/服务命名中不出现"围标"等敏感词。
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from plugins.ddw_bid_writer.models import BidDocument, BidProject
from plugins.ddw_bid_writer.services.style_service import (
    STYLE_PROFILES,
    StyleService,
)

# ---------------------------------------------------------------------------
# 脱敏约束：源代码中不得出现"围标"等敏感词
# ---------------------------------------------------------------------------


SENSITIVE_WORDS = ["围标", "串标", "陪标", "买标", "卖标", "泄标", "暗标"]


def test_no_sensitive_words_in_source():
    """源代码扫描：不允许出现围标等敏感词（注释/字符串/函数名）。"""
    from pathlib import Path

    plugin_dir = Path(__file__).resolve().parents[1]
    # 扫描所有 .py 和 .html
    targets = list(plugin_dir.rglob("*.py")) + list(plugin_dir.rglob("*.html"))
    violations: list[str] = []
    for f in targets:
        # 跳过 tests
        if "/tests/" in str(f):
            continue
        text = f.read_text(encoding="utf-8")
        for w in SENSITIVE_WORDS:
            if w in text:
                # 找出上下文
                idx = text.find(w)
                ctx = text[max(0, idx - 30):idx + 30].replace("\n", "\\n")
                violations.append(f"{f.name}: '{w}' -> ...{ctx}...")
    assert not violations, "检测到敏感词：\n" + "\n".join(violations)


def test_no_sensitive_words_in_manifest():
    from pathlib import Path

    m = Path(__file__).resolve().parents[1] / "manifest.yaml"
    text = m.read_text(encoding="utf-8")
    for w in SENSITIVE_WORDS:
        assert w not in text, f"manifest.yaml 出现敏感词：{w}"


# ---------------------------------------------------------------------------
# 单元：StyleService
# ---------------------------------------------------------------------------


def test_style_service_valid_styles():
    sty = StyleService()
    assert set(sty.VALID_STYLES) >= {"标准", "保守", "激进", "创新型"}


def test_style_profiles_definitions():
    for s in ("标准", "保守", "激进", "创新型"):
        assert s in STYLE_PROFILES
        assert "tone_words" in STYLE_PROFILES[s]
        assert "forbidden_phrases" in STYLE_PROFILES[s]


@pytest.mark.asyncio
async def test_refine_rejects_invalid_style(db_session, style_service):
    d = BidDocument(bid_project_id=1, doc_type="技术标", style="标准",
                    content="测试内容", version=1, status="draft")
    db_session.add(d)
    await db_session.commit()
    with pytest.raises(ValueError, match="不支持的风格"):
        await style_service.refine(db_session, d, target_style="围标")


@pytest.mark.asyncio
async def test_refine_creates_new_version(db_session, style_service):
    d = BidDocument(
        bid_project_id=1, doc_type="技术标", style="标准",
        content="本项目采用稳妥可靠的方案，沿用既有工艺。",
        version=1, status="draft",
    )
    db_session.add(d)
    await db_session.commit()

    new_doc, diff = await style_service.refine(db_session, d, target_style="激进")
    await db_session.commit()
    assert new_doc.id != d.id
    assert new_doc.version == 2
    assert new_doc.style == "激进"
    # 风格词替换：原"沿用"应被替换为"突破"
    assert "突破" in new_doc.content or "创新" in new_doc.content
    assert "标准 → 激进" in diff


# ---------------------------------------------------------------------------
# 单元：ReviewService
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_review_detects_sensitive_words(db_session, review_service):
    d = BidDocument(
        bid_project_id=1, doc_type="技术标", style="标准",
        content="# 项目\n## 章节\n本方案采用围标方式运作",  # 敏感词
        version=1, status="draft",
    )
    db_session.add(d)
    await db_session.commit()
    result = await review_service.review(db_session, d)
    await db_session.commit()
    sensitive_issues = [i for i in result["issues"] if i["category"] == "敏感词"]
    assert len(sensitive_issues) == 1
    assert sensitive_issues[0]["severity"] == "error"
    assert result["score"] < 100


@pytest.mark.asyncio
async def test_review_clean_doc(db_session, review_service):
    d = BidDocument(
        bid_project_id=1, doc_type="技术标", style="标准",
        content=(
            "# 武汉光谷住宅项目技术标\n\n"
            "## 一、项目理解\n本项目类型为住宅，估算金额 5 亿元。联系电话：13912345678。\n\n"
            "## 二、技术方案\n本项目采用框剪结构，遵循国家规范 GB50010。\n\n"
            "## 三、进度计划\n总工期 24 个月。"
        ),
        version=1, status="draft",
    )
    db_session.add(d)
    await db_session.commit()
    result = await review_service.review(db_session, d)
    await db_session.commit()
    # 干净文档应该没有 error
    errors = [i for i in result["issues"] if i["severity"] == "error"]
    assert len(errors) == 0
    assert result["score"] >= 80


@pytest.mark.asyncio
async def test_review_short_doc_warns(db_session, review_service):
    d = BidDocument(
        bid_project_id=1, doc_type="技术标", style="标准",
        content="# 项目",  # 太短
        version=1, status="draft",
    )
    db_session.add(d)
    await db_session.commit()
    result = await review_service.review(db_session, d)
    await db_session.commit()
    assert result["score"] < 90


# ---------------------------------------------------------------------------
# 集成：项目 CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_project_crud(db_session, seeded_tenant):

    p = BidProject(
        tenant_id=seeded_tenant,
        project_name="光谷A住宅投标",
        client_name="光谷置业",
        project_type="住宅",
        estimated_amount=5e8,
        bid_deadline=datetime.now() + timedelta(days=30),
    )
    db_session.add(p)
    await db_session.commit()
    assert p.id is not None

    g = (
        await db_session.execute(
            __import__("sqlalchemy").select(BidProject).where(BidProject.id == p.id)
        )
    ).scalar_one_or_none()
    assert g is not None
    assert g.client_name == "光谷置业"


# ---------------------------------------------------------------------------
# 集成：模板 CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_template_crud(db_session, template_service, seeded_tenant):
    t = await template_service.create(db_session, {
        "tenant_id": seeded_tenant,
        "name": "标准技术标模板",
        "doc_type": "技术标",
        "content": "## 标准模板\n正文...",
        "is_default": True,
    })
    await db_session.commit()
    assert t.id is not None
    # 列表
    total, items = await template_service.list(db_session)
    assert total == 1
    # 按 doc_type 过滤
    total2, _ = await template_service.list(db_session, doc_type="商务标")
    assert total2 == 0
    # 更新
    t2 = await template_service.update(db_session, t.id, {"name": "更新后名称"})
    assert t2.name == "更新后名称"
    # 删除
    ok = await template_service.delete(db_session, t.id)
    assert ok is True


@pytest.mark.asyncio
async def test_template_default_uniqueness(db_session, template_service, seeded_tenant):
    """同 doc_type 下只能有一个默认模板。"""
    t1 = await template_service.create(db_session, {
        "tenant_id": seeded_tenant, "name": "T1", "doc_type": "技术标",
        "content": "x", "is_default": True,
    })
    await db_session.commit()
    # 创建第二个默认模板
    t2 = await template_service.create(db_session, {
        "tenant_id": seeded_tenant, "name": "T2", "doc_type": "技术标",
        "content": "y", "is_default": True,
    })
    await db_session.commit()
    # 第一个的 is_default 应当被自动取消
    t1_db = await template_service.get(db_session, t1.id)
    assert t1_db.is_default is False or t1_db.is_default == 0
    assert t2.is_default is True or t2.is_default == 1


# ---------------------------------------------------------------------------
# 集成：GenerateService
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_basic(db_session, generate_service, seeded_tenant):

    p = BidProject(
        tenant_id=seeded_tenant,
        project_name="武汉商业综合体",
        client_name="武汉置业",
        project_type="商业",
        estimated_amount=8e8,
        bid_deadline=datetime.now() + timedelta(days=60),
    )
    db_session.add(p)
    await db_session.commit()

    doc = await generate_service.generate(db_session, p, doc_type="技术标", style="标准", mode="legacy")
    await db_session.commit()

    assert doc.id is not None
    assert doc.bid_project_id == p.id
    assert doc.doc_type == "技术标"
    assert doc.style == "标准"
    assert "武汉商业综合体" in doc.content
    assert "## 1. " in doc.content  # 章节标题
    assert doc.version == 1
    assert p.status == "generating"


@pytest.mark.asyncio
async def test_generate_with_template(db_session, generate_service, template_service, seeded_tenant):

    # 准备默认模板
    tpl = await template_service.create(db_session, {
        "tenant_id": seeded_tenant, "name": "商务标模板",
        "doc_type": "商务标", "content": "## 模板前言\n应严格遵循商务条款。",
        "is_default": True,
    })
    await db_session.commit()

    p = BidProject(
        tenant_id=seeded_tenant,
        project_name="光谷商务",
        project_type="商业",
    )
    db_session.add(p)
    await db_session.commit()

    doc = await generate_service.generate(db_session, p, doc_type="商务标", style="保守", mode="legacy", template_id=tpl.id)
    await db_session.commit()
    assert "模板前言" in doc.content  # 模板内容嵌入了


@pytest.mark.asyncio
async def test_generate_different_doc_types(db_session, generate_service, seeded_tenant):

    p = BidProject(tenant_id=seeded_tenant, project_name="测试项目", project_type="住宅")
    db_session.add(p)
    await db_session.commit()

    for dt in ("技术标", "商务标", "资格预审"):
        doc = await generate_service.generate(db_session, p, doc_type=dt, style="标准", mode="legacy")
        await db_session.commit()
        # 各 doc_type 的章节标题不同
        if dt == "技术标":
            assert "技术方案" in doc.content
        elif dt == "商务标":
            assert "投标函" in doc.content
        elif dt == "资格预审":
            assert "申请人" in doc.content


# ---------------------------------------------------------------------------
# 集成：完整流程
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_workflow(db_session, generate_service, style_service, review_service, seeded_tenant):
    """端到端：建项目 → 生成 → 修饰 → 审查。"""

    # 1. 建项目
    p = BidProject(
        tenant_id=seeded_tenant,
        project_name="全流程测试",
        project_type="住宅",
        estimated_amount=3e8,
    )
    db_session.add(p)
    await db_session.commit()

    # 2. 生成
    doc = await generate_service.generate(db_session, p, doc_type="技术标", style="标准")
    await db_session.commit()

    # 3. 风格修饰
    refined, diff = await style_service.refine(db_session, doc, target_style="保守")
    await db_session.commit()
    assert refined.version == 2
    assert "标准 → 保守" in diff

    # 4. 审查
    result = await review_service.review(db_session, refined)
    await db_session.commit()
    assert result["document_id"] == refined.id
    assert 0 <= result["score"] <= 100
    assert refined.status == "reviewed"


# ---------------------------------------------------------------------------
# Router 路径
# ---------------------------------------------------------------------------


def test_router_has_25_endpoints():
    """v2.0 — 增加 C+D+E+F 9 个端点，共 25 个。"""
    from plugins.ddw_bid_writer.router import build_router

    class P:
        name = "ddw-bid-writer"
        template_service = type("S", (), {})()
        generate_service = type("S", (), {})()
        style_service = type("S", (), {})()
        review_service = type("S", (), {})()

    r = build_router(P())
    collected = {}
    for route in r.routes:
        if not hasattr(route, "methods"):
            continue
        if getattr(route, "include_in_schema", True) is False:
            continue
        for m in route.methods:
            collected.setdefault(route.path, set()).add(m)

    total = sum(len(s) for s in collected.values())
    # v1.0: 16 endpoints
    # v2.0: +9 endpoints（C+D+E+F: knowledge×3, importance×1, plan×1, sections×4）
    # = 25 endpoints
    assert total == 26, f"expected 26 endpoints, got {total}: {collected}"

    prefix = "/api/v1/plugins/ddw-bid-writer"
    # 关键端点都在
    must_have = [
        (f"{prefix}/projects", "POST"),
        (f"{prefix}/projects", "GET"),
        (f"{prefix}/projects/{{project_id}}/generate", "POST"),
        (f"{prefix}/projects/{{project_id}}/plan", "POST"),
        (f"{prefix}/projects/{{project_id}}/assess-importance", "POST"),
        (f"{prefix}/documents/{{doc_id}}/sections", "GET"),
        (f"{prefix}/documents/{{doc_id}}/sections/{{section_index}}/regenerate", "POST"),
        (f"{prefix}/documents/{{doc_id}}/sections/{{section_index}}/lock", "POST"),
        (f"{prefix}/documents/{{doc_id}}/sections/{{section_index}}/unlock", "POST"),
        (f"{prefix}/knowledge/bootstrap", "POST"),
        (f"{prefix}/knowledge/status", "GET"),
        (f"{prefix}/knowledge/templates", "GET"),
    ]
    for path, method in must_have:
        assert path in collected, f"missing path: {path}"
        assert method in collected[path], f"missing method {method} on {path}"
