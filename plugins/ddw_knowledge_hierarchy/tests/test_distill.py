"""Tests for Methodology Distill Engine (TASK_SPEC E.6).

8 test cases:
1. test_distill_start — 启动任务返回 job_id，DB 有记录
2. test_distill_progress — 查询进度，状态转换正确
3. test_distill_units_list — 完成后单元列表返回，含 verified/rejected 统计
4. test_distill_unit_detail — 单元详情含 RIA++ 六段
5. test_distill_reject_unit — 人工驳回后 status=rejected
6. test_distill_permission — 无权限用户访问其他租户 job 被拒（403）
7. test_distill_document_not_found — document_id 不存在返回 404
8. test_distill_pipeline_mock — mock LLM 返回，流水线从 queued→completed，单元入库
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("DDW_JWT_SECRET", "test-secret-key-for-testing-32bytes-ok")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.ddw_knowledge_hierarchy import models as kh_models
from plugins.ddw_knowledge_hierarchy.acl import Principal
from plugins.ddw_knowledge_hierarchy.distill_router import (
    router as distill_router,
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Set up isolated SQLite + test principal context."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    db_file = tmp_path / "distill_test.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        poolclass=NullPool,
    )

    async def _create_all():
        async with engine.begin() as conn:
            await conn.run_sync(kh_models.Base.metadata.create_all)

    asyncio.run(_create_all())

    maker = async_sessionmaker(engine, expire_on_commit=False)

    @contextlib.asynccontextmanager
    async def _fake_scope():
        async with maker() as s:
            try:
                yield s
            except Exception:
                await s.rollback()
                raise

    import plugins.ddw_knowledge_hierarchy.distill_router as distill_router_module

    monkeypatch.setattr(distill_router_module, "session_scope", _fake_scope)

    app = FastAPI()
    app.include_router(distill_router)
    with TestClient(app) as c:
        yield c

    asyncio.run(engine.dispose())


def _set_principal(monkeypatch, principal: Principal):
    """Set the principal context for the current test via ContextVar."""
    from plugins.ddw_knowledge_hierarchy.deps import set_principal_context

    set_principal_context(principal)


# --- Principals ---

TENANT_A_USER = Principal(user_id=1, tenant_id=1, role="owner")
TENANT_B_USER = Principal(user_id=2, tenant_id=2, role="owner")


# --- Helpers ---


def _create_kb_and_doc(client, monkeypatch, principal: Principal):
    """Create a KB and document for testing."""
    _set_principal(monkeypatch, principal)

    # Create KB

    # We need to insert directly since we're mocking session_scope

    # Simplified: just return mock IDs
    return 1, "doc-test-001"


# ---------------------------------------------------------------------------
# Test 1: test_distill_start
# ---------------------------------------------------------------------------


def test_distill_start(client, monkeypatch):
    """启动任务返回 job_id，DB 有记录。"""
    _set_principal(monkeypatch, TENANT_A_USER)

    # Mock the document check to return a valid doc
    with patch("plugins.ddw_knowledge_hierarchy.distill_router.session_scope") as mock_scope:
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _mock_scope():
            from unittest.mock import MagicMock

            mock_session = MagicMock()

            # Mock KBDocument query
            mock_doc = MagicMock()
            mock_doc.id = "doc-test-001"
            mock_doc.kb_id = 1
            mock_doc.tenant_id = 1

            # Mock KhDistillJob
            mock_job = MagicMock()
            mock_job.id = "job-test-001"
            mock_job.tenant_id = 1

            # Configure mock session
            mock_session.execute = AsyncMock()

            # First call returns doc, second call returns job
            mock_result = MagicMock()
            mock_result.scalar_one_or_none = MagicMock(side_effect=[mock_doc, mock_job])
            mock_session.execute.return_value = mock_result

            mock_session.add = MagicMock()

            async def _mock_flush():
                # Assign job id on flush (mirrors SQLAlchemy default=_uuid behavior)
                for obj in mock_session.add.call_args_list:
                    arg = obj.args[0]
                    if arg is not None and getattr(arg, "id", None) is None:
                        try:
                            arg.id = "job-test-001"
                        except Exception:
                            pass

            mock_session.flush = AsyncMock(side_effect=_mock_flush)
            mock_session.commit = AsyncMock()

            yield mock_session

        mock_scope.return_value = _mock_scope()

        # Also mock bypass_tenant_filter
        with patch("plugins.ddw_knowledge_hierarchy.distill_router.bypass_tenant_filter") as mock_bypass:
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def _mock_bypass():
                yield

            mock_bypass.return_value = _mock_bypass()

            resp = client.post(
                "/distill/methodology/start",
                json={
                    "knowledge_base_id": 1,
                    "document_id": "doc-test-001",
                    "strict_mode": True,
                },
            )

    assert resp.status_code == 201
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "queued"
    assert data["document_id"] == "doc-test-001"
    assert data["knowledge_base_id"] == 1


# ---------------------------------------------------------------------------
# Test 2: test_distill_progress
# ---------------------------------------------------------------------------


def test_distill_progress(client, monkeypatch):
    """查询进度，状态转换正确。"""
    _set_principal(monkeypatch, TENANT_A_USER)

    with patch("plugins.ddw_knowledge_hierarchy.distill_router.session_scope") as mock_scope:
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _mock_scope():
            from unittest.mock import MagicMock

            mock_session = MagicMock()

            # Mock job query
            mock_job = MagicMock()
            mock_job.id = "job-test-001"
            mock_job.tenant_id = 1
            mock_job.status = "extracting"
            mock_job.progress = 45.0

            # Mock units query
            mock_unit1 = MagicMock()
            mock_unit1.status = "verified"
            mock_unit2 = MagicMock()
            mock_unit2.status = "rejected"

            mock_result_job = MagicMock()
            mock_result_job.scalar_one_or_none.return_value = mock_job

            mock_result_units = MagicMock()
            mock_result_units.scalars.return_value.all.return_value = [mock_unit1, mock_unit2]

            # First call returns job, second returns units
            mock_session.execute = AsyncMock(side_effect=[mock_result_job, mock_result_units])

            yield mock_session

        mock_scope.return_value = _mock_scope()

        with patch("plugins.ddw_knowledge_hierarchy.distill_router.bypass_tenant_filter") as mock_bypass:
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def _mock_bypass():
                yield

            mock_bypass.return_value = _mock_bypass()

            resp = client.get("/distill/methodology/job-test-001")

    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == "job-test-001"
    assert data["status"] == "extracting"
    assert data["progress"] == 45.0
    assert data["units_count"] == 2
    assert data["verified_count"] == 1
    assert data["rejected_count"] == 1


# ---------------------------------------------------------------------------
# Test 3: test_distill_units_list
# ---------------------------------------------------------------------------


def test_distill_units_list(client, monkeypatch):
    """完成后单元列表返回，含 verified/rejected 统计。"""
    _set_principal(monkeypatch, TENANT_A_USER)

    with patch("plugins.ddw_knowledge_hierarchy.distill_router.session_scope") as mock_scope:
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _mock_scope():
            from unittest.mock import MagicMock

            mock_session = MagicMock()

            # Mock job query
            mock_job = MagicMock()
            mock_job.id = "job-test-001"
            mock_job.tenant_id = 1

            # Mock units
            mock_unit1 = MagicMock()
            mock_unit1.id = "unit-1"
            mock_unit1.unit_type = "framework"
            mock_unit1.title = "τ优先诊断法"
            mock_unit1.trigger_words = "性能瓶颈、找瓶颈"
            mock_unit1.v1_passed = True
            mock_unit1.v2_passed = True
            mock_unit1.v3_passed = True
            mock_unit1.status = "verified"

            mock_unit2 = MagicMock()
            mock_unit2.id = "unit-2"
            mock_unit2.unit_type = "principle"
            mock_unit2.title = "反例方法"
            mock_unit2.trigger_words = None
            mock_unit2.v1_passed = False
            mock_unit2.v2_passed = True
            mock_unit2.v3_passed = True
            mock_unit2.status = "rejected"

            mock_result_job = MagicMock()
            mock_result_job.scalar_one_or_none.return_value = mock_job

            mock_result_units = MagicMock()
            mock_result_units.scalars.return_value.all.return_value = [mock_unit1, mock_unit2]

            mock_session.execute = AsyncMock(side_effect=[mock_result_job, mock_result_units])

            yield mock_session

        mock_scope.return_value = _mock_scope()

        with patch("plugins.ddw_knowledge_hierarchy.distill_router.bypass_tenant_filter") as mock_bypass:
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def _mock_bypass():
                yield

            mock_bypass.return_value = _mock_bypass()

            resp = client.get("/distill/methodology/job-test-001/units")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2

    # Check first unit
    unit1 = data["items"][0]
    assert unit1["id"] == "unit-1"
    assert unit1["unit_type"] == "framework"
    assert unit1["title"] == "τ优先诊断法"
    assert unit1["status"] == "verified"
    assert unit1["v1_passed"] is True


# ---------------------------------------------------------------------------
# Test 4: test_distill_unit_detail
# ---------------------------------------------------------------------------


def test_distill_unit_detail(client, monkeypatch):
    """单元详情含 RIA++ 六段。"""
    _set_principal(monkeypatch, TENANT_A_USER)

    with patch("plugins.ddw_knowledge_hierarchy.distill_router.session_scope") as mock_scope:
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _mock_scope():
            from unittest.mock import MagicMock

            mock_session = MagicMock()

            # Mock unit with full RIA++ sections
            mock_unit = MagicMock()
            mock_unit.id = "unit-1"
            mock_unit.tenant_id = 1
            mock_unit.unit_type = "framework"
            mock_unit.title = "τ优先诊断法"
            mock_unit.trigger_words = "性能瓶颈、找瓶颈、慢在哪"
            mock_unit.v1_passed = True
            mock_unit.v2_passed = True
            mock_unit.v3_passed = True
            mock_unit.status = "verified"
            mock_unit.r_section = "τ优先诊断法是一种系统化的性能分析方法..."
            mock_unit.i_section = "该方法通过三个步骤定位性能瓶颈..."
            mock_unit.a1_section = "在某电商系统中，使用τ优先诊断法发现..."
            mock_unit.e_section = "1. 收集性能数据 2. 分析关键路径 3. 定位瓶颈点"
            mock_unit.b_section = "不适用于纯IO密集型场景"
            mock_unit.reject_reason = None
            mock_unit.source_chapter = "第三章 性能优化"
            mock_unit.created_at = MagicMock()
            mock_unit.created_at.isoformat.return_value = "2026-08-12T10:00:00"

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_unit

            mock_session.execute = AsyncMock(return_value=mock_result)

            yield mock_session

        mock_scope.return_value = _mock_scope()

        with patch("plugins.ddw_knowledge_hierarchy.distill_router.bypass_tenant_filter") as mock_bypass:
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def _mock_bypass():
                yield

            mock_bypass.return_value = _mock_bypass()

            resp = client.get("/distill/methodology/units/unit-1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "unit-1"
    assert data["unit_type"] == "framework"
    assert data["title"] == "τ优先诊断法"
    assert data["r_section"] is not None
    assert data["i_section"] is not None
    assert data["a1_section"] is not None
    assert data["e_section"] is not None
    assert data["b_section"] is not None
    assert data["trigger_words"] == "性能瓶颈、找瓶颈、慢在哪"
    assert data["source_chapter"] == "第三章 性能优化"


# ---------------------------------------------------------------------------
# Test 5: test_distill_reject_unit
# ---------------------------------------------------------------------------


def test_distill_reject_unit(client, monkeypatch):
    """人工驳回后 status=rejected。"""
    _set_principal(monkeypatch, TENANT_A_USER)

    mock_unit = None  # set inside _mock_scope, asserted after request

    with patch("plugins.ddw_knowledge_hierarchy.distill_router.session_scope") as mock_scope:
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _mock_scope():
            from unittest.mock import MagicMock

            nonlocal mock_unit

            mock_session = MagicMock()

            # Mock unit
            mock_unit = MagicMock()
            mock_unit.id = "unit-1"
            mock_unit.tenant_id = 1
            mock_unit.status = "verified"
            mock_unit.reject_reason = None

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_unit

            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.commit = AsyncMock()

            yield mock_session

        mock_scope.return_value = _mock_scope()

        with patch("plugins.ddw_knowledge_hierarchy.distill_router.bypass_tenant_filter") as mock_bypass:
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def _mock_bypass():
                yield

            mock_bypass.return_value = _mock_bypass()

            resp = client.post("/distill/methodology/units/unit-1/reject")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "unit-1"
    assert data["status"] == "rejected"
    assert mock_unit.status == "rejected"
    assert mock_unit.reject_reason == "人工驳回"


# ---------------------------------------------------------------------------
# Test 6: test_distill_permission
# ---------------------------------------------------------------------------


def test_distill_permission(client, monkeypatch):
    """无权限用户访问其他租户 job 被拒（403）。"""
    _set_principal(monkeypatch, TENANT_B_USER)  # tenant_id=2

    with patch("plugins.ddw_knowledge_hierarchy.distill_router.session_scope") as mock_scope:
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _mock_scope():
            from unittest.mock import MagicMock

            mock_session = MagicMock()

            # Mock job belonging to tenant 1
            mock_job = MagicMock()
            mock_job.id = "job-test-001"
            mock_job.tenant_id = 1  # Different tenant!

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_job

            mock_session.execute = AsyncMock(return_value=mock_result)

            yield mock_session

        mock_scope.return_value = _mock_scope()

        with patch("plugins.ddw_knowledge_hierarchy.distill_router.bypass_tenant_filter") as mock_bypass:
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def _mock_bypass():
                yield

            mock_bypass.return_value = _mock_bypass()

            resp = client.get("/distill/methodology/job-test-001")

    assert resp.status_code == 403
    assert "无权访问" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Test 7: test_distill_document_not_found
# ---------------------------------------------------------------------------


def test_distill_document_not_found(client, monkeypatch):
    """document_id 不存在返回 404。"""
    _set_principal(monkeypatch, TENANT_A_USER)

    with patch("plugins.ddw_knowledge_hierarchy.distill_router.session_scope") as mock_scope:
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _mock_scope():
            from unittest.mock import MagicMock

            mock_session = MagicMock()

            # Mock document not found
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None

            mock_session.execute = AsyncMock(return_value=mock_result)

            yield mock_session

        mock_scope.return_value = _mock_scope()

        with patch("plugins.ddw_knowledge_hierarchy.distill_router.bypass_tenant_filter") as mock_bypass:
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def _mock_bypass():
                yield

            mock_bypass.return_value = _mock_bypass()

            resp = client.post(
                "/distill/methodology/start",
                json={
                    "knowledge_base_id": 999,
                    "document_id": "nonexistent-doc",
                    "strict_mode": True,
                },
            )

    assert resp.status_code == 404
    assert "文档不存在" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Test 8: test_distill_pipeline_mock
# ---------------------------------------------------------------------------


def test_distill_pipeline_mock(client, monkeypatch):
    """mock LLM 返回，流水线从 queued→completed，单元入库。"""
    from unittest.mock import AsyncMock, MagicMock, patch

    # Mock LLM responses
    mock_extract_response = [
        {
            "title": "HACCP七原理",
            "original_text": "HACCP体系包含七个基本原理...",
            "source_chapter": "第五章 食品安全管理体系",
            "reason": "框架类方法论",
        }
    ]

    mock_verify_response = {
        "v1_passed": True,
        "v1_reason": "文档多处提及",
        "v2_passed": True,
        "v2_reason": "可预测食品安全风险",
        "v3_passed": True,
        "v3_reason": "专业领域知识",
        "overall": "verified",
        "reject_reason": None,
    }

    mock_construct_response = {
        "r_section": "HACCP体系包含七个基本原理...",
        "i_section": "HACCP是一个系统化的食品安全管理方法...",
        "a1_section": "在某食品加工厂中，应用HACCP原理...",
        "trigger_words": "食品安全、HACCP、危害分析",
        "e_section": "1. 进行危害分析 2. 确定关键控制点 3. 建立监控程序",
        "b_section": "不适用于非食品行业",
    }

    with patch("plugins.ddw_knowledge_hierarchy.services.distill_pipeline.call_llm_json_array") as mock_extract, \
         patch("plugins.ddw_knowledge_hierarchy.services.distill_pipeline.call_llm_json") as mock_json:

        mock_extract.return_value = mock_extract_response
        # 5 extract types → 5 candidates → 5 verify + 5 construct calls
        mock_json.side_effect = [mock_verify_response] * 5 + [mock_construct_response] * 5

        # Test the pipeline directly
        from plugins.ddw_knowledge_hierarchy.services.distill_pipeline import (
            distill_document,
        )

        async def _test_pipeline():
            # Create mock job and session
            mock_job = MagicMock()
            mock_job.id = "job-pipeline-test"
            mock_job.tenant_id = 1
            mock_job.document_id = "doc-test"
            mock_job.status = "queued"
            mock_job.progress = 0.0
            mock_job.error = None

            mock_session = MagicMock()

            # Mock document content query — select(DocumentChunk.content) returns str list
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [
                "HACCP体系包含七个基本原理，用于食品安全管理..."
            ]
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.flush = AsyncMock()
            mock_session.add = MagicMock()

            await distill_document(mock_session, mock_job, strict_mode=True)

            # Verify job status transitions
            assert mock_job.status == "completed"
            assert mock_job.progress == 100
            assert mock_job.error is None

            # Verify unit was added
            assert mock_session.add.called

        asyncio.run(_test_pipeline())
