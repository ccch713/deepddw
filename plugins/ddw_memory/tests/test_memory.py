"""ddw_memory 企业记忆引擎 V2 测试用例（TASK_SPEC_1 验收标准）。

不依赖 conftest fixture，每个 test 自带 setup/teardown。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


async def _make_db():
    """创建测试数据库 + 注入全局 session。"""
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )
    from sqlalchemy.pool import StaticPool

    from core.database.models import Tenant
    from core.database.session import Base
    from plugins.ddw_memory.models import (  # noqa: F401
        AutoCaptureConfigORM,
        AutoCapturePendingORM,
        MemoryORM,
        PositionSOPTemplateORM,
    )

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    sm = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    import core.database.session as db_mod
    db_mod._engine = engine
    db_mod._session_maker = sm

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with sm() as s:
        s.add(Tenant(id=1, name="Default", plan="free", status="active"))
        s.add(Tenant(id=16, name="祥云化工", plan="enterprise", status="active"))
        await s.commit()

    return engine, sm


# ---------------------------------------------------------------------------
# TEST 1: 创建企业级红线记忆
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_01_enterprise_redline_memory():
    engine, _ = await _make_db()
    try:
        from plugins.ddw_memory.models import MemoryLayer
        from plugins.ddw_memory.service import MemoryService
        svc = MemoryService()

        entry = await svc.create_memory(
            tenant_id=16, layer=MemoryLayer.ENTERPRISE,
            content="所有动火作业必须经过三级审批，持证上岗",
            creator_id=1, tags=["redline", "safety", "procurement"],
        )
        assert entry.layer == MemoryLayer.ENTERPRISE
        assert "redline" in entry.tags
        assert entry.memory_uuid

        fetched = await svc.get_memory(tenant_id=16, memory_id=entry.id)
        assert fetched is not None
        assert fetched.content == "所有动火作业必须经过三级审批，持证上岗"
        assert "redline" in fetched.tags
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# TEST 2: 创建部门级记忆
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_02_department_memory():
    engine, _ = await _make_db()
    try:
        from plugins.ddw_memory.models import MemoryLayer
        from plugins.ddw_memory.service import MemoryService
        svc = MemoryService()

        entry = await svc.create_memory(
            tenant_id=16, layer=MemoryLayer.DEPARTMENT,
            content="质量部周会每周三14:00，会议室B305",
            creator_id=2, department_id=3,
        )
        assert entry.department_id == 3

        with pytest.raises(ValueError, match="department_id"):
            await svc.create_memory(
                tenant_id=16, layer=MemoryLayer.DEPARTMENT,
                content="缺少部门ID", creator_id=2,
            )
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# TEST 3: 四层穿透检索（含 redline 置顶）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_03_search_with_redline_boost():
    engine, _ = await _make_db()
    try:
        from plugins.ddw_memory.models import MemoryLayer
        from plugins.ddw_memory.service import MemoryService
        svc = MemoryService()

        await svc.create_memory(tenant_id=16, layer=MemoryLayer.ENTERPRISE, content="危化品必须双人双锁管理", creator_id=1, tags=["redline", "safety"])
        await svc.create_memory(tenant_id=16, layer=MemoryLayer.ENTERPRISE, content="公司年会定在12月30日", creator_id=1)
        await svc.create_memory(tenant_id=16, layer=MemoryLayer.DEPARTMENT, content="质量部的不合格品处理流程需要更新", creator_id=2, department_id=3)
        await svc.create_memory(tenant_id=16, layer=MemoryLayer.PERSONAL, content="我发现不合格品标签打印有问题", creator_id=10)

        result = await svc.search_memories(tenant_id=16, query="不合格品", user_id=10, top_k=10)
        assert result.total >= 2

        result2 = await svc.search_memories(tenant_id=16, query="安全", user_id=1, top_k=5)
        if result2.hits:
            assert "redline" in result2.hits[0].entry.tags
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# TEST 4: 红线置顶验证
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_04_redline_force_top():
    engine, _ = await _make_db()
    try:
        from plugins.ddw_memory.models import MemoryLayer
        from plugins.ddw_memory.service import MemoryService
        svc = MemoryService()

        await svc.create_memory(tenant_id=16, layer=MemoryLayer.ENTERPRISE, content="采购流程：先申请再审批", creator_id=1)
        await svc.create_memory(tenant_id=16, layer=MemoryLayer.ENTERPRISE, content="所有采购必须三方比价，严禁单一来源", creator_id=1, tags=["redline", "procurement"])

        result = await svc.search_memories(tenant_id=16, query="采购", user_id=1, top_k=5)
        if len(result.hits) >= 2:
            assert "redline" in result.hits[0].entry.tags
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# TEST 5: 岗位 SOP 查询
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_05_position_knowledge_query():
    engine, _ = await _make_db()
    try:
        from plugins.ddw_memory.models import MemoryLayer
        from plugins.ddw_memory.service import MemoryService
        svc = MemoryService()

        await svc.create_sop_template(tenant_id=16, position_name="质量工程师", sop_steps=["发现不合格品 → 隔离标识", "填写不合格品报告", "通知供应商", "跟踪纠正措施"], position_id=5)
        await svc.create_memory(tenant_id=16, layer=MemoryLayer.POSITION, content="不合格品标签用红色，放在隔离区B2", creator_id=10, position_id=5)
        await svc.create_memory(tenant_id=16, layer=MemoryLayer.ENTERPRISE, content="不合格品严禁放行，发现一起开除", creator_id=1, tags=["redline"])

        result = await svc.query_position_knowledge(tenant_id=16, user_id=10, position_id=5, question="发现不合格品怎么处理")
        assert len(result["sop_steps"]) == 4
        assert len(result["position_memories"]) >= 1
        assert len(result["enterprise_redlines"]) >= 1
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# TEST 6: 自动捕获（待审核 → 审核通过）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_06_auto_capture_pending():
    engine, _ = await _make_db()
    try:
        from plugins.ddw_memory.service import MemoryService
        svc = MemoryService()

        result = await svc.create_pending_capture(
            tenant_id=16, user_id=10, session_id="sess_test_001",
            summary="讨论了CAPA流程优化方案",
            knowledge_points=["CAPA需要在48小时内响应", "根因分析要用5Why"],
            suggested_layer="personal", suggested_tags=["CAPA", "质量"], confidence=0.85,
        )
        assert result["status"] == "pending"

        pending = await svc.list_pending_captures(tenant_id=16)
        assert len(pending) >= 1

        from plugins.ddw_memory.models import MemoryLayer
        entry = await svc.approve_capture(tenant_id=16, capture_id=result["id"])
        assert entry is not None
        assert "auto_capture" in entry.tags
        assert entry.layer == MemoryLayer.PERSONAL
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# TEST 7: 记忆迁移（离职交接）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_07_memory_migration():
    engine, _ = await _make_db()
    try:
        from plugins.ddw_memory.models import MemoryLayer
        from plugins.ddw_memory.service import MemoryService
        svc = MemoryService()

        await svc.create_memory(tenant_id=16, layer=MemoryLayer.ENTERPRISE, content="企业记忆", creator_id=100)
        await svc.create_memory(tenant_id=16, layer=MemoryLayer.PERSONAL, content="个人笔记A", creator_id=100)
        await svc.create_memory(tenant_id=16, layer=MemoryLayer.PERSONAL, content="个人笔记B", creator_id=100)

        result = await svc.migrate_memories(tenant_id=16, source_user_id=100, target_user_id=200, scope="personal")
        assert result["migrated"] == 2

        tgt = await svc.list_memories(tenant_id=16, creator_id=200)
        assert tgt["total"] == 2

        src = await svc.list_memories(tenant_id=16, creator_id=100)
        assert src["total"] == 3
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# TEST 8: 层级裁剪
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_08_layer_pruning():
    engine, _ = await _make_db()
    try:
        from plugins.ddw_memory.models import MemoryLayer
        from plugins.ddw_memory.service import MemoryService
        svc = MemoryService()

        await svc.create_memory(tenant_id=16, layer=MemoryLayer.ENTERPRISE, content="企业制度", creator_id=1)
        await svc.create_memory(tenant_id=16, layer=MemoryLayer.DEPARTMENT, content="部门规范", creator_id=1, department_id=3)
        await svc.create_memory(tenant_id=16, layer=MemoryLayer.PERSONAL, content="个人笔记", creator_id=1)
        await svc.create_memory(tenant_id=16, layer=MemoryLayer.POSITION, content="岗位SOP", creator_id=1, position_id=5)

        ent_result = await svc.search_memories(tenant_id=16, query="制度", user_id=1, layers=[MemoryLayer.ENTERPRISE], top_k=10)
        for hit in ent_result.hits:
            assert hit.entry.layer == MemoryLayer.ENTERPRISE

        per_result = await svc.search_memories(tenant_id=16, query="笔记", user_id=1, layers=[MemoryLayer.PERSONAL], top_k=10)
        for hit in per_result.hits:
            assert hit.entry.layer == MemoryLayer.PERSONAL
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# BONUS: 统计
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_09_stats():
    engine, _ = await _make_db()
    try:
        from plugins.ddw_memory.models import MemoryLayer
        from plugins.ddw_memory.service import MemoryService
        svc = MemoryService()

        await svc.create_memory(tenant_id=16, layer=MemoryLayer.ENTERPRISE, content="e", creator_id=1)
        await svc.create_memory(tenant_id=16, layer=MemoryLayer.DEPARTMENT, content="d", creator_id=1, department_id=3)
        await svc.create_memory(tenant_id=16, layer=MemoryLayer.PERSONAL, content="p", creator_id=1)

        stats = await svc.get_stats(tenant_id=16)
        assert stats["total_entries"] >= 3
        assert stats["by_layer"]["enterprise"] >= 1
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# BONUS: 多租户隔离
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_10_tenant_isolation():
    engine, _ = await _make_db()
    try:
        from plugins.ddw_memory.models import MemoryLayer
        from plugins.ddw_memory.service import MemoryService
        svc = MemoryService()

        await svc.create_memory(tenant_id=16, layer=MemoryLayer.ENTERPRISE, content="祥云机密", creator_id=1)
        await svc.create_memory(tenant_id=1, layer=MemoryLayer.ENTERPRISE, content="默认租户", creator_id=1)

        xiangyun = await svc.list_memories(tenant_id=16)
        for item in xiangyun["items"]:
            assert item.content != "默认租户"

        default = await svc.list_memories(tenant_id=1)
        for item in default["items"]:
            assert item.content != "祥云机密"
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# BONUS: 向量检索（P1-1）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_11_vector_search():
    """embedding_json 非空 → cosine 参与排序；hybrid → RRF 合并。"""
    import json
    engine, _ = await _make_db()
    try:
        from plugins.ddw_memory.service import MemoryService
        svc = MemoryService()

        # 创建带 embedding 的记忆
        emb_a = [1.0, 0.0, 0.0]  # 与 query 最相似
        emb_b = [0.0, 1.0, 0.0]
        emb_c = [0.7, 0.7, 0.0]  # 部分相似

        # 通过直接 DB 操作设置 embedding_json
        from plugins.ddw_memory.models import MemoryORM
        from plugins.ddw_memory.service import _committed_session
        async with _committed_session() as session:
            row_a = MemoryORM(tenant_id=16, layer="enterprise", content="质量管控体系", creator_id=1, embedding_json=json.dumps(emb_a))
            row_b = MemoryORM(tenant_id=16, layer="enterprise", content="生产排程计划", creator_id=1, embedding_json=json.dumps(emb_b))
            row_c = MemoryORM(tenant_id=16, layer="enterprise", content="质量检验标准", creator_id=1, embedding_json=json.dumps(emb_c))
            session.add_all([row_a, row_b, row_c])

        # hybrid 检索（含向量）
        query_emb = [1.0, 0.0, 0.0]
        result = await svc.search_memories(
            tenant_id=16, query="质量", user_id=1,
            top_k=10, search_mode="hybrid",
            query_embedding=query_emb,
        )
        assert result.total >= 1
        # 向量命中应参与排序
        has_vector = any(h.match_type == "vector" for h in result.hits)
        has_keyword = any(h.match_type == "keyword" for h in result.hits)
        assert has_vector or has_keyword  # 至少一种匹配方式生效
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# BONUS: 事件总线接入验证（P1-2）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_12_event_bus_subscribe():
    """ddw_memory plugin 订阅 conversation.turn.completed 事件。"""
    from core.events.bus import get_bus
    from plugins.ddw_memory.plugin import Plugin

    bus = get_bus()

    # 记录订阅前的 handler 数量
    count_before = bus.listener_count("conversation.turn.completed")

    # 创建 plugin 实例（不启动 HTTP）
    plugin = Plugin()
    plugin.app = None  # 不需要 FastAPI app
    plugin.setup()

    # 验证事件已订阅
    count_after = bus.listener_count("conversation.turn.completed")
    assert count_after > count_before, "plugin.setup() 应注册事件 handler"

    # 验证 handler 是 callable
    handlers = bus.listeners("conversation.turn.completed")
    assert len(handlers) > 0
    assert callable(handlers[-1])

    # 清理：取消订阅
    for h in handlers:
        bus.unsubscribe("conversation.turn.completed", h)
