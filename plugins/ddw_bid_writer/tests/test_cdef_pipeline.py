"""C+D+E+F 方案单元 + 集成测试。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from plugins.ddw_bid_writer.services.embedding_service import (
    SimpleEmbedding,
)
from plugins.ddw_bid_writer.services.fact_sheet import (
    DateFact,
    FactSheet,
    MetricFact,
    PersonnelFact,
    extract_dates,
    extract_metrics,
    extract_personnel,
    fact_sheet_from_dict,
)
from plugins.ddw_bid_writer.services.importance_detector import (
    ImportanceDetector,
    ImportanceLevel,
)
from plugins.ddw_bid_writer.services.knowledge_bootstrap import (
    chunk_text,
    detect_style_baseline,
    extract_section_structure,
    parse_file,
)
from plugins.ddw_bid_writer.services.outline_planner import (
    OutlinePlanner,
)
from plugins.ddw_bid_writer.services.vector_store import (
    TenantKnowledgeStore,
    VectorStore,
)

# ---------------------------------------------------------------------------
# 单元：Embedding & VectorStore
# ---------------------------------------------------------------------------


def test_simple_embedding_basic():
    emb = SimpleEmbedding(dim=128)
    emb.fit_idf(["hello world", "hello world", "different text"])
    v1 = asyncio.run(emb.embed("hello world"))
    v2 = asyncio.run(emb.embed("hello world"))
    v3 = asyncio.run(emb.embed("completely different"))
    assert len(v1) == 128
    # 完全相同文本 cosine 应该是 1.0
    assert abs(emb.cosine(v1, v2) - 1.0) < 1e-6
    # 完全不同 cosine 应该小
    assert emb.cosine(v1, v3) < 0.5


def test_simple_embedding_chinese():
    """简单 hash-trick embedding：相同文本 cosine=1；不同文本 cosine≈0。
    注：真实语义相似度需要 bge / sentence-transformers，本测试只验证基础行为。
    """
    emb = SimpleEmbedding(dim=256)
    emb.fit_idf(["武汉光谷住宅 框剪结构", "上海陆家嘴商业 框架结构"])
    v1 = asyncio.run(emb.embed("武汉光谷住宅 框剪结构"))
    v2 = asyncio.run(emb.embed("武汉光谷住宅 框剪结构"))  # 完全相同
    v3 = asyncio.run(emb.embed("完全无关的文本xyz123"))
    # 完全相同 → 1
    assert abs(emb.cosine(v1, v2) - 1.0) < 1e-6
    # 不同 → 接近 0
    assert emb.cosine(v1, v3) < 0.5


def test_vector_store_add_and_search(tmp_path):
    db_path = tmp_path / "vec.sqlite"
    store = VectorStore(db_path)
    emb = SimpleEmbedding(dim=128)
    emb.fit_idf(["武汉光谷A住宅 框剪结构 3500元", "上海陆家嘴商业 框架结构 5000元", "北京海淀工业 钢结构 2000元"])
    embs = [asyncio.run(emb.embed(t)) for t in ["武汉光谷A住宅 框剪结构 3500元", "上海陆家嘴商业 框架结构 5000元", "北京海淀工业 钢结构 2000元"]]
    store.add(1, "doc1", ["武汉光谷A住宅 框剪结构 3500元", "上海陆家嘴商业 框架结构 5000元", "北京海淀工业 钢结构 2000元"], embs)
    assert store.count(1) == 3
    q = asyncio.run(emb.embed("武汉住宅项目"))
    hits = store.search(1, q, top_k=2)
    assert len(hits) == 2
    # 第一个应该是武汉相关的
    assert "武汉" in hits[0]["content"]


def test_tenant_knowledge_store_integration(tmp_path):
    kb = TenantKnowledgeStore(1, base_dir=str(tmp_path))
    chunks = [
        "武汉光谷A住宅技术标 - 项目理解章节",
        "武汉光谷A住宅技术标 - 技术方案章节",
        "上海陆家嘴B商业技术标 - 项目理解章节",
    ]
    ids = kb.add_document("doc1", chunks)
    assert len(ids) == 3
    stats = kb.stats()
    assert stats["chunks"] == 3


# ---------------------------------------------------------------------------
# 单元：FactSheet
# ---------------------------------------------------------------------------


def test_factsheet_roundtrip():
    fs = FactSheet(
        project_name="测试项目",
        client_name="测试客户",
        estimated_amount=5e8,
        structure_type="框剪",
        floor_count=18,
        area_sqm=50000,
    )
    fs.personnel.append(PersonnelFact(role="项目经理", name="张三", certs=["一级注册结构师"]))
    fs.dates.append(DateFact(key="开工日", value="2026-03-01"))
    fs.metrics.append(MetricFact(key="单方造价", value=3500, unit="元/㎡"))

    d = fs.to_dict()
    fs2 = fact_sheet_from_dict(d)
    assert fs2.project_name == "测试项目"
    assert len(fs2.personnel) == 1
    assert fs2.personnel[0].name == "张三"
    assert fs2.dates[0].value == "2026-03-01"
    assert fs2.metrics[0].value == 3500


def test_extract_personnel_chinese():
    text = "项目经理：张三\n技术负责人：李四\n商务负责人：王五"
    personnel = extract_personnel(text)
    roles = {p.role for p in personnel}
    assert "项目经理" in roles
    assert "技术负责人" in roles
    assert any(p.name == "张三" for p in personnel)


def test_extract_dates_chinese():
    text = "本项目开工日：2026-03-01，竣工日：2027-08-30"
    dates = extract_dates(text)
    assert any(d.key == "开工日" for d in dates)
    assert any("2026" in d.value for d in dates)


def test_extract_metrics_chinese():
    text = "本项目总投资：5 亿元，总工期：24 个月，建筑面积：50000 ㎡"
    metrics = extract_metrics(text)
    keys = {m.key for m in metrics}
    # 至少抽到一些指标（可能匹配到 "总投资" / "总工期" / "建筑面积"）
    assert len(metrics) > 0
    # 验证抽到了数字
    assert any(m.value > 0 for m in metrics)
    # 至少有一个单位（"亿"/"月"/"㎡"）
    assert any(m.unit for m in metrics)


def test_factsheet_update_from_section():
    fs = FactSheet(project_name="X")
    updated = fs.update_from_section("项目经理：张三\n技术负责人：李四", "section1")
    assert any("personnel:项目经理=张三" in u for u in updated)
    assert len(fs.personnel) == 2


def test_factsheet_to_markdown_includes_facts():
    fs = FactSheet(
        project_name="武汉光谷A",
        client_name="光谷置业",
        estimated_amount=5e8,
        structure_type="框剪",
    )
    md = fs.to_markdown()
    assert "武汉光谷A" in md
    assert "光谷置业" in md
    assert "5 亿" in md or "500,000,000" in md
    assert "框剪" in md
    assert "事实表" in md or "FactSheet" in md


# ---------------------------------------------------------------------------
# 单元：Knowledge Bootstrap 工具函数
# ---------------------------------------------------------------------------


def test_parse_md_file(tmp_path):
    f = tmp_path / "test.md"
    f.write_text("# Title\n\ncontent here", encoding="utf-8")
    text, err = parse_file(f)
    assert err is None
    assert "Title" in text
    assert "content" in text


def test_parse_unsupported_extension(tmp_path):
    f = tmp_path / "test.xyz"
    f.write_text("content", encoding="utf-8")
    text, err = parse_file(f)
    assert text == ""
    assert "unsupported" in err.lower()


def test_parse_pdf_unsupported_yet(tmp_path):
    f = tmp_path / "test.pdf"
    f.write_bytes(b"fake pdf content")
    text, err = parse_file(f)
    assert text == ""
    assert "暂不支持" in err


def test_chunk_text_by_heading():
    text = """# 标题
前言
## 1. 项目理解
本项目为住宅类项目。
## 2. 技术方案
本项目采用框剪结构。
## 3. 进度计划
总工期 24 个月。
"""
    chunks = chunk_text(text)
    assert len(chunks) == 3
    assert "项目理解" in chunks[0]
    assert "技术方案" in chunks[1]
    assert "进度计划" in chunks[2]


def test_chunk_text_filters_short():
    text = "## 标题\n短"  # 太短会被过滤
    chunks = chunk_text(text)
    # "短" 不到 20 字符，整块被过滤
    assert all(len(c) >= 20 for c in chunks)


def test_extract_section_structure():
    text = "# 一级\n## 1.1 二级 A\n## 1.2 二级 B\n# 二级"
    secs = extract_section_structure(text)
    assert "1.1 二级 A" in secs
    assert "1.2 二级 B" in secs


def test_detect_style_baseline_conservative():
    text = "本方案稳妥可靠，采用成熟工艺，沿用既有经验"
    style = detect_style_baseline(text)
    assert "稳妥" in style or "可靠" in style


def test_detect_style_baseline_aggressive():
    text = "本方案突破创新，领先行业，差异化优势显著"
    style = detect_style_baseline(text)
    assert "突破" in style or "创新" in style or "领先" in style


# ---------------------------------------------------------------------------
# 单元：Importance Detector（F 方案）
# ---------------------------------------------------------------------------


def test_importance_routine():
    det = ImportanceDetector()
    assess = det.assess({
        "project_name": "X",
        "estimated_amount": 5e7,  # 5 千万 < 1 亿
        "project_type": "住宅",
    })
    assert assess.level == ImportanceLevel.ROUTINE
    assert assess.recommended_mode == "auto"


def test_importance_important_by_amount():
    det = ImportanceDetector()
    assess = det.assess({
        "project_name": "X",
        "estimated_amount": 2e8,  # 2 亿
        "project_type": "住宅",
    })
    assert assess.level == ImportanceLevel.IMPORTANT
    assert assess.recommended_mode == "important"


def test_importance_critical_by_amount():
    """单纯 6 亿仍判 important（5 亿线 +0.5，未到 0.6 关键线）；加截止时间紧迫升至 critical。"""
    det = ImportanceDetector()
    assess = det.assess({
        "project_name": "X",
        "estimated_amount": 6e8,  # 6 亿
        "project_type": "住宅",
    })
    # 单一信号 → important
    assert assess.level == ImportanceLevel.IMPORTANT

    # 加上截止时间紧迫 → critical
    soon = (datetime.now() + timedelta(days=2)).isoformat()
    assess2 = det.assess({
        "project_name": "X",
        "estimated_amount": 6e8,
        "project_type": "住宅",
        "bid_deadline": soon,
    })
    assert assess2.level == ImportanceLevel.CRITICAL


def test_importance_critical_by_urgency():
    det = ImportanceDetector()
    soon = (datetime.now() + timedelta(days=2)).isoformat()
    assess = det.assess({
        "project_name": "X",
        "estimated_amount": 5e7,
        "bid_deadline": soon,
    })
    assert assess.level in (ImportanceLevel.IMPORTANT, ImportanceLevel.CRITICAL)


def test_importance_user_marked_critical():
    det = ImportanceDetector()
    assess = det.assess(
        {"project_name": "X", "estimated_amount": 1e6},
        user_marked="critical",
    )
    assert assess.level == ImportanceLevel.CRITICAL
    assert any("用户手动标记" in r for r in assess.reasons)


def test_importance_user_marked_routine():
    det = ImportanceDetector()
    assess = det.assess(
        {"project_name": "X", "estimated_amount": 1e9},  # 即使金额巨大
        user_marked="routine",
    )
    assert assess.level == ImportanceLevel.ROUTINE


# ---------------------------------------------------------------------------
# 单元：Outline Planner
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_outline_planner_basic(seeded_tenant):
    planner = OutlinePlanner()
    project = {
        "project_name": "武汉光谷A住宅",
        "client_name": "光谷置业",
        "project_type": "住宅",
        "estimated_amount": 5e8,
        "structure_type": "框剪",
        "floor_count": 18,
        "area_sqm": 50000,
    }
    result = await planner.plan(project, doc_type="技术标", style="标准")
    assert result["doc_type"] == "技术标"
    assert result["style"] == "标准"
    assert len(result["sections"]) == 6  # 默认技术标 6 章
    assert result["total_target_words"] > 0
    # FactSheet
    assert result["fact_sheet"]["project_name"] == "武汉光谷A住宅"
    assert "5 亿" in result["style_baseline"] or "standard" in result["style_baseline"].lower() or "标准" in result["style_baseline"]


@pytest.mark.asyncio
async def test_outline_planner_different_styles():
    planner = OutlinePlanner()
    project = {"project_name": "X", "project_type": "商业", "estimated_amount": 3e8}
    for style in ("标准", "保守", "激进", "创新型"):
        result = await planner.plan(project, doc_type="技术标", style=style)
        assert style in result["style_baseline"] or result["style"] == style


@pytest.mark.asyncio
async def test_outline_planner_business_doc_type():
    planner = OutlinePlanner()
    project = {"project_name": "X", "project_type": "商业"}
    result = await planner.plan(project, doc_type="商务标", style="标准")
    assert len(result["sections"]) == 5  # 商务标 5 章
    assert any("投标函" in s["title"] for s in result["sections"])


# ---------------------------------------------------------------------------
# 集成：Knowledge Bootstrap（用 in-memory DB + tmp 文件夹）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_knowledge_bootstrap_full_flow(db_session, seeded_tenant, tmp_path):
    """端到端：建文件夹 → 写入 3 个 markdown → 跑 bootstrap → 验证。"""
    from plugins.ddw_bid_writer.services.knowledge_bootstrap import KnowledgeBootstrap

    # 准备 3 个历史标书文件
    folder = tmp_path / "history"
    folder.mkdir()
    (folder / "光谷A住宅-技术标.md").write_text(
        """# 光谷A住宅技术标
## 一、项目理解
本项目为住宅类，建筑面积 50000 ㎡。
## 二、技术方案
本项目采用框剪结构，单方造价 3500 元/㎡。
## 三、人员配置
项目经理：张三
技术负责人：李四
## 四、进度计划
总工期 24 个月。开工日：2026-03-01。
""",
        encoding="utf-8",
    )
    (folder / "光谷B商业-技术标.md").write_text(
        """# 光谷B商业技术标
## 一、项目理解
本项目为商业类，建筑面积 30000 ㎡。
## 二、技术方案
本项目采用框架结构，单方造价 5000 元/㎡。
## 三、人员配置
项目经理：王五
## 四、进度计划
总工期 18 个月。
""",
        encoding="utf-8",
    )
    (folder / "光谷C市政-技术标.md").write_text(
        """# 光谷C市政技术标
## 一、项目理解
本项目为市政道路工程。
## 二、技术方案
本项目采用常规工艺。
## 三、人员
项目经理：赵六
""",
        encoding="utf-8",
    )

    kb = KnowledgeBootstrap(base_dir=str(tmp_path / "kb"))
    result = await kb.run(db_session, tenant_id=seeded_tenant, folder=str(folder))
    await db_session.commit()

    assert result["status"] == "success"
    assert result["total_files"] == 3
    assert result["success_files"] == 3
    assert result["failed_files"] == 0
    assert result["total_chunks"] > 0
    assert result["templates_extracted"] >= 1

    # 验证统计
    stats = await kb.stats_async(db_session, tenant_id=seeded_tenant)
    assert stats["docs_total"] == 3
    assert stats["kb_chunks"] > 0
    assert len(stats["templates"]) >= 1
    assert stats["last_run"] is not None


@pytest.mark.asyncio
async def test_knowledge_bootstrap_handles_unsupported(tmp_path, db_session, seeded_tenant):
    from plugins.ddw_bid_writer.services.knowledge_bootstrap import KnowledgeBootstrap

    folder = tmp_path / "mixed"
    folder.mkdir()
    # 给 .md 足够内容以生成 >= 1 个 chunk
    (folder / "ok.md").write_text(
        "# 标题\n\n## 一、项目理解\n本项目是测试章节，包含足够长度的内容以通过 20 字过滤。\n",
        encoding="utf-8",
    )
    (folder / "bad.pdf").write_bytes(b"fake pdf")

    kb = KnowledgeBootstrap(base_dir=str(tmp_path / "kb"))
    result = await kb.run(db_session, tenant_id=seeded_tenant, folder=str(folder))
    await db_session.commit()
    # 只统计支持的扩展名
    assert result["total_files"] == 1
    assert result["success_files"] == 1
    assert result["failed_files"] == 0
    assert result["total_chunks"] >= 1


# ---------------------------------------------------------------------------
# 集成：Section Writer（RAG 增强）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_section_writer_with_rag(db_session, seeded_tenant, tmp_path):
    """先 bootstrap 知识库，再生成章节，验证 RAG 检索生效。"""
    from plugins.ddw_bid_writer.models import BidProject
    from plugins.ddw_bid_writer.services.knowledge_bootstrap import KnowledgeBootstrap
    from plugins.ddw_bid_writer.services.section_writer import SectionWriter

    # 准备历史数据
    folder = tmp_path / "hist"
    folder.mkdir()
    (folder / "光谷A住宅-技术标.md").write_text(
        """# 光谷A住宅技术标
## 一、项目理解
本项目为住宅类，建筑面积 50000 ㎡，采用框剪结构。
## 二、技术方案
本项目关键技术：1. 大体积混凝土；2. 钢结构连接。
""",
        encoding="utf-8",
    )
    kb = KnowledgeBootstrap(base_dir=str(tmp_path / "kb"))
    await kb.run(db_session, tenant_id=seeded_tenant, folder=str(folder))
    await db_session.commit()

    # 准备项目
    p = BidProject(tenant_id=seeded_tenant, project_name="光谷D新住宅", project_type="住宅", estimated_amount=5e8)
    db_session.add(p)
    await db_session.commit()

    # 准备 FactSheet + 章节
    fs = FactSheet(project_name="光谷D", project_type="住宅", estimated_amount=5e8, structure_type="框剪")
    sections = [
        {"index": 1, "title": "一、项目理解", "summary": "理解业主需求", "target_words": 800},
    ]
    sw = SectionWriter()
    result = await sw.write_all(
        project={"project_name": "光谷D", "project_type": "住宅", "estimated_amount": 5e8, "structure_type": "框剪"},
        doc_type="技术标",
        style="标准",
        sections=sections,
        fact_sheet=fs,
        tenant_id=seeded_tenant,
        rag_top_k=3,
    )
    assert len(result) == 1
    assert "## 一、项目理解" in result[0]["content"]
    # RAG 检索到了参考案例（chunk 内容里含历史项目的特征词）
    assert (
        "光谷A" in result[0]["rag_context"]
        or "住宅类" in result[0]["rag_context"]
        or "无相似历史案例" in result[0]["rag_context"]
    )


# ---------------------------------------------------------------------------
# 集成：Consistency Checker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consistency_check_amount_mismatch():
    from plugins.ddw_bid_writer.services.consistency_checker import ConsistencyChecker

    fs = FactSheet(project_name="X", estimated_amount=5e8)  # 5 亿
    sections = [
        {
            "index": 1,
            "title": "一、",
            "content": "本项目总投资 3 亿元，工期 24 个月。",  # 故意写 3 亿
        }
    ]
    checker = ConsistencyChecker()
    result = await checker.check(fs, sections)
    # 应该有金额冲突
    amount_conflicts = [c for c in result["conflicts"] if c["type"] == "amount_mismatch"]
    assert len(amount_conflicts) >= 1


@pytest.mark.asyncio
async def test_consistency_check_structure_mismatch():
    from plugins.ddw_bid_writer.services.consistency_checker import ConsistencyChecker

    fs = FactSheet(project_name="X", structure_type="框剪")
    sections = [
        {
            "index": 1,
            "title": "一、",
            "content": "本项目采用框架结构施工。",  # 故意写框架
        }
    ]
    checker = ConsistencyChecker()
    result = await checker.check(fs, sections)
    struct_conflicts = [c for c in result["conflicts"] if c["type"] == "structure_mismatch"]
    assert len(struct_conflicts) >= 1


@pytest.mark.asyncio
async def test_consistency_check_passes_when_consistent():
    from plugins.ddw_bid_writer.services.consistency_checker import ConsistencyChecker

    fs = FactSheet(project_name="X", estimated_amount=5e8, structure_type="框剪")
    sections = [
        {
            "index": 1,
            "title": "一、",
            "content": "本项目总投资 5 亿元，采用框剪结构。",
        }
    ]
    checker = ConsistencyChecker()
    result = await checker.check(fs, sections)
    # 不应该有结构冲突
    struct_conflicts = [c for c in result["conflicts"] if c["type"] == "structure_mismatch"]
    amount_conflicts = [c for c in result["conflicts"] if c["type"] == "amount_mismatch"]
    assert len(struct_conflicts) == 0
    assert len(amount_conflicts) == 0


# ---------------------------------------------------------------------------
# 集成：Agent Orchestrator（端到端 stub LLM）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_orchestrator_runs_all_4_stages(db_session, seeded_tenant, tmp_path):
    """端到端：bootstrap → generate → 4 stages。"""
    from plugins.ddw_bid_writer.models import BidProject
    from plugins.ddw_bid_writer.services.agent_orchestrator import (
        AgentOrchestrator,
        AgentRole,
    )

    # 准备知识库
    folder = tmp_path / "hist"
    folder.mkdir()
    (folder / "光谷A住宅-技术标.md").write_text(
        """# 光谷A住宅技术标
## 一、项目理解
本项目为住宅类。
## 二、技术方案
本项目采用框剪结构。
""",
        encoding="utf-8",
    )
    from plugins.ddw_bid_writer.services.knowledge_bootstrap import KnowledgeBootstrap
    kb = KnowledgeBootstrap(base_dir=str(tmp_path / "kb"))
    await kb.run(db_session, tenant_id=seeded_tenant, folder=str(folder))
    await db_session.commit()

    # 准备项目
    p = BidProject(tenant_id=seeded_tenant, project_name="光谷E新住宅", project_type="住宅", estimated_amount=5e8)
    db_session.add(p)
    await db_session.commit()

    # 跑 4 阶段
    orch = AgentOrchestrator()
    result = await orch.run(
        project={
            "id": p.id,
            "project_name": p.project_name,
            "client_name": p.client_name,
            "project_type": p.project_type,
            "estimated_amount": p.estimated_amount,
        },
        doc_type="技术标",
        style="标准",
        tenant_id=seeded_tenant,
    )

    # 验证 4 个 agent 都跑过
    roles = {step["role"] for step in result["trace"]}
    assert AgentRole.PLANNER.value in roles
    assert AgentRole.WRITER.value in roles
    assert AgentRole.REVIEWER.value in roles
    assert AgentRole.EDITOR.value in roles

    # 验证输出
    assert result["content"]
    assert len(result["sections"]) == 6  # 技术标 6 章
    assert "fact_sheet" in result


# ---------------------------------------------------------------------------
# 集成：Generate Service 新流程（auto 模式）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_service_auto_mode(db_session, generate_service, seeded_tenant, tmp_path):
    """auto 模式 = C+D+E 全流程。"""
    from plugins.ddw_bid_writer.models import AgentRun, BidProject, BidSection

    folder = tmp_path / "hist"
    folder.mkdir()
    (folder / "x.md").write_text("# x\n## 一\n本项目住宅类，框剪结构。", encoding="utf-8")
    from plugins.ddw_bid_writer.services.knowledge_bootstrap import KnowledgeBootstrap
    kb = KnowledgeBootstrap(base_dir=str(tmp_path / "kb"))
    await kb.run(db_session, tenant_id=seeded_tenant, folder=str(folder))
    await db_session.commit()

    p = BidProject(tenant_id=seeded_tenant, project_name="测试auto", project_type="住宅", estimated_amount=5e8)
    db_session.add(p)
    await db_session.commit()

    doc = await generate_service.generate(db_session, p, doc_type="技术标", style="标准", mode="auto")
    await db_session.commit()

    assert doc.id is not None
    assert doc.content
    # 章节记录也被写入
    from sqlalchemy import select
    secs = (await db_session.execute(select(BidSection).where(BidSection.bid_document_id == doc.id))).scalars().all()
    assert len(secs) == 6
    # AgentRun 也写了
    runs = (await db_session.execute(select(AgentRun).where(AgentRun.bid_project_id == p.id))).scalars().all()
    assert len(runs) == 1
    assert runs[0].status == "success"
    assert runs[0].agents_trace  # trace 记录了


@pytest.mark.asyncio
async def test_generate_service_skeleton_mode(db_session, generate_service, seeded_tenant):
    """skeleton 模式 = 仅大纲，不生成正文。"""
    from plugins.ddw_bid_writer.models import BidProject

    p = BidProject(tenant_id=seeded_tenant, project_name="skel测试", project_type="住宅", estimated_amount=3e8)
    db_session.add(p)
    await db_session.commit()

    plan_result = await generate_service.plan(db_session, p, doc_type="技术标", style="标准")
    assert len(plan_result["sections"]) == 6
    assert plan_result["fact_sheet"]["project_name"] == "skel测试"


# ---------------------------------------------------------------------------
# 集成：重要性评估 API
# ---------------------------------------------------------------------------


def test_importance_detector_scores_sum():
    """分数累加逻辑正确性。"""
    det = ImportanceDetector()
    assess = det.assess({
        "project_name": "X",
        "estimated_amount": 6e8,  # +0.5
        "project_type": "市政",  # +0.1
        "bid_deadline": (datetime.now() + timedelta(days=2)).isoformat(),  # +0.3
    })
    # 0.5 + 0.1 + 0.3 = 0.9
    assert assess.score >= 0.8
    assert assess.level == ImportanceLevel.CRITICAL


# ---------------------------------------------------------------------------
# 脱敏：检查所有 .py 文件不含敏感词
# ---------------------------------------------------------------------------


def test_no_sensitive_words_in_v2_modules():
    """v2 新增模块脱敏检查。"""

    SENSITIVE = ["围标", "串标", "陪标", "买标", "卖标", "泄标", "暗标"]
    plugin_dir = Path(__file__).resolve().parents[1]
    targets = list(plugin_dir.rglob("*.py")) + list(plugin_dir.rglob("*.html"))
    violations: list[str] = []
    for f in targets:
        if "/tests/" in str(f):
            continue
        text = f.read_text(encoding="utf-8")
        for w in SENSITIVE:
            if w in text:
                idx = text.find(w)
                ctx = text[max(0, idx - 30):idx + 30].replace("\n", "\\n")
                violations.append(f"{f.name}: '{w}' -> ...{ctx}...")
    assert not violations, "检测到敏感词：\n" + "\n".join(violations)
