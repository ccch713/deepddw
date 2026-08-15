"""ddw_memory_knowledge_bridge 测试用例（6 条，TASK_SPEC_2 验收标准）。

不依赖外部数据库，用 mock 函数模拟记忆引擎和知识库引擎。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


# ── Mock 函数 ──────────────────────────────────────────────

async def _mock_memory_search(**kwargs):
    """模拟记忆引擎检索。"""
    return [
        {"id": 1, "content": "CAPA流程：发现不合格→隔离→根因分析→纠正→验证", "summary": "CAPA流程概述", "score": 0.9, "layer": "department", "created_at": None},
        {"id": 2, "content": "不合格品严禁放行", "summary": "红线", "score": 0.8, "layer": "enterprise", "created_at": None},
    ]


async def _mock_knowledge_search(**kwargs):
    """模拟知识库检索。"""
    return [
        {"id": "doc_001", "content": "CAPA管理程序文件，包含纠正措施和预防措施的详细流程", "summary": "CAPA管理程序", "score": 0.85, "doc_title": "CAPA管理程序"},
    ]


async def _mock_memory_get(tenant_id, memory_id):
    """模拟获取记忆条目。"""
    memories = {
        1: {"id": 1, "content": "CAPA流程：发现→隔离→纠正", "tags": ["CAPA", "质量"], "layer": "department"},
        2: {"id": 2, "content": "采购红线：必须三方比价", "tags": ["redline", "procurement"], "layer": "enterprise"},
    }
    return memories.get(memory_id)


async def _mock_kb_upload(**kwargs):
    return {"id": "new_doc_001"}


async def _mock_kb_get(doc_id):
    return {"title": f"文档#{doc_id}", "content": "CAPA管理程序文件内容，包含纠正措施和预防措施的详细流程描述"}


async def _mock_memory_create(**kwargs):
    return {"id": 99, **kwargs}


async def _mock_llm_chat(system, user):
    return '{"bucket": "质量知识桶", "tags": ["CAPA"], "confidence": 0.9, "reasoning": "内容涉及质量管控"}'


# ── 测试 ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_01_unified_search():
    """统一检索：同时返回记忆和知识库结果。"""
    from plugins.ddw_memory_knowledge_bridge.models import UnifiedSearchReq
    from plugins.ddw_memory_knowledge_bridge.service import unified_search

    req = UnifiedSearchReq(query="CAPA流程", search_memory=True, search_knowledge=True, user_id=1)
    result = await unified_search(
        tenant_id=1, req=req,
        memory_search_fn=_mock_memory_search,
        knowledge_search_fn=_mock_knowledge_search,
    )
    assert result.total >= 2
    assert result.memory_count >= 1
    assert result.knowledge_count >= 1
    # 来源标注正确
    sources = [h.source for h in result.hits]
    assert "memory" in sources
    assert "knowledge" in sources
    print(f"T1 PASS: {result.total} hits ({result.memory_count} mem + {result.knowledge_count} kb)")


@pytest.mark.asyncio
async def test_02_memory_archive():
    """记忆归档到知识库，分类正确。"""
    from plugins.ddw_memory_knowledge_bridge.service import (
        archive_memories_to_knowledge,
    )

    result = await archive_memories_to_knowledge(
        tenant_id=1,
        memory_ids=[1, 2],
        target_bucket=None,
        auto_classify=True,
        memory_get_fn=_mock_memory_get,
        knowledge_upload_fn=_mock_kb_upload,
        llm_chat_fn=_mock_llm_chat,
        available_buckets=["质量知识桶", "流程知识桶"],
    )
    assert result["archived"] == 2
    assert result["failed"] == 0
    print(f"T2 PASS: archived={result['archived']}")


@pytest.mark.asyncio
async def test_03_knowledge_import():
    """知识文档导入为 position 级记忆。"""
    from plugins.ddw_memory_knowledge_bridge.service import import_knowledge_to_memory

    created = []
    async def _track_create(**kwargs):
        created.append(kwargs)
        return {"id": len(created)}

    result = await import_knowledge_to_memory(
        tenant_id=1,
        document_ids=["doc_001"],
        target_layer="position",
        department_id=None,
        position_id=5,
        knowledge_get_fn=_mock_kb_get,
        memory_create_fn=_track_create,
    )
    assert result["imported"] == 1
    assert result["failed"] == 0
    assert created[0]["layer"] == "position"
    assert created[0]["position_id"] == 5
    print(f"T3 PASS: imported={result['imported']}, layer={created[0]['layer']}")


@pytest.mark.asyncio
async def test_04_auto_archive():
    """自动归档：模拟高价值记忆归档。"""
    from plugins.ddw_memory_knowledge_bridge.service import (
        archive_memories_to_knowledge,
    )

    # 模拟3个用户检索过的记忆
    result = await archive_memories_to_knowledge(
        tenant_id=1,
        memory_ids=[1],
        target_bucket="质量知识桶",
        auto_classify=False,
        memory_get_fn=_mock_memory_get,
        knowledge_upload_fn=_mock_kb_upload,
    )
    assert result["archived"] >= 1
    print(f"T4 PASS: auto archived={result['archived']}")


@pytest.mark.asyncio
async def test_05_redline_cross_system():
    """红线跨系统：知识库红线文档导入 enterprise 记忆。"""
    from plugins.ddw_memory_knowledge_bridge.service import import_knowledge_to_memory

    async def _redline_kb_get(doc_id):
        return {"title": "采购红线规定", "content": "所有采购必须三方比价，严禁单一来源，违反者开除"}

    async def _redline_llm(system, user):
        return '{"summary": "采购红线：三方比价", "key_points": ["三方比价"], "applicable_positions": ["采购"], "has_redlines": true, "suggested_tags": ["redline"]}'

    created = []
    async def _track_create(**kwargs):
        created.append(kwargs)
        return {"id": len(created)}

    result = await import_knowledge_to_memory(
        tenant_id=1,
        document_ids=["redline_doc"],
        target_layer="department",
        department_id=None,
        position_id=None,
        knowledge_get_fn=_redline_kb_get,
        memory_create_fn=_track_create,
        llm_chat_fn=_redline_llm,
    )
    assert result["imported"] == 1
    # 有红线 → 强制 enterprise 层
    assert created[0]["layer"] == "enterprise"
    assert "redline" in created[0]["tags"]
    print(f"T5 PASS: redline → layer={created[0]['layer']}, tags={created[0]['tags']}")


@pytest.mark.asyncio
async def test_06_classify_accuracy():
    """LLM 分类准确性。"""
    from plugins.ddw_memory_knowledge_bridge.llm_classify import classify_content

    result = await classify_content(
        content="不合格品处理流程：发现→隔离→通知供应商",
        tags=["质量", "不合格品"],
        layer="department",
        available_buckets=["质量知识桶", "流程知识桶", "法规知识桶"],
        llm_chat_fn=_mock_llm_chat,
    )
    assert result["confidence"] >= 0.5
    assert result["suggested_bucket"]  # 非空
    print(f"T6 PASS: bucket={result['suggested_bucket']}, confidence={result['confidence']}")


# ── 运行所有测试 ──────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_01_unified_search,
        test_02_memory_archive,
        test_03_knowledge_import,
        test_04_auto_archive,
        test_05_redline_cross_system,
        test_06_classify_accuracy,
    ]
    for t in tests:
        asyncio.run(t())
    print("\n=== ALL 6 TESTS PASSED ===")
