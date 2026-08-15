"""集成测试：HTTP 端点（search / chat SSE / health）+ 上传组件测试。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_project_root = str(Path(__file__).resolve().parents[3])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from fastapi import APIRouter, FastAPI
from fastapi.responses import StreamingResponse
from httpx import ASGITransport, AsyncClient

from plugins.ddw_ent_knowledge.core.embedding import SimpleEmbedding
from plugins.ddw_ent_knowledge.core.vector_store import VectorStore
from plugins.ddw_ent_knowledge.schemas import ChatRequest, SearchRequest, SearchResponse
from plugins.ddw_ent_knowledge.services.ingest_service import IngestService
from plugins.ddw_ent_knowledge.services.retrieval_service import RetrievalService


def _make_app(tmp_path: str):
    """构建测试用 FastAPI app（无 DB 依赖）。"""
    db_path = os.path.join(tmp_path, "vectors.sqlite")
    emb = SimpleEmbedding(dim=512)
    vs = VectorStore(db_path)
    retrieval = RetrievalService(emb, vs)

    router = APIRouter(prefix="/api/v1/plugins/ddw-ent-knowledge")

    @router.post("/search", response_model=SearchResponse)
    async def search(req: SearchRequest) -> SearchResponse:
        result = await retrieval.search(1, req.query, top_k=req.top_k)
        return SearchResponse(hits=result["hits"], took_ms=result["took_ms"])

    @router.post("/chat")
    async def chat(req: ChatRequest):
        search_result = await retrieval.search(1, req.query, top_k=req.top_k)
        kb_took_ms = search_result["took_ms"]
        hits = search_result["hits"]

        async def event_generator():
            meta = {"kb_took_ms": kb_took_ms, "hit_count": len(hits)}
            yield f"data: {json.dumps({'type': 'meta', **meta})}\n\n"
            fallback = hits[0]["content"][:300] if hits else "暂无相关信息"
            yield f"data: {json.dumps({'type': 'token', 'token': fallback})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'elapsed_ms': 42, 'fallback': True})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"X-KB-Took-Ms": str(kb_took_ms)},
        )

    @router.get("/health")
    async def health():
        return {
            "plugin": "ddw_ent_knowledge",
            "version": "1.0.0",
            "status": "ok",
            "embedding": emb.name,
            "chunks": vs.count(1),
        }

    app = FastAPI()
    app.include_router(router)
    return app, emb, vs


@pytest.fixture()
def app_and_services(tmp_path):
    return _make_app(str(tmp_path))


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health(self, app_and_services):
        app, emb, vs = app_and_services
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/plugins/ddw-ent-knowledge/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["plugin"] == "ddw_ent_knowledge"
        assert data["status"] == "ok"
        assert data["embedding"] == "simple-hash-tfidf"
        assert data["chunks"] == 0


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class TestSearchEndpoint:
    @pytest.mark.asyncio
    async def test_search_returns_hits(self, app_and_services):
        app, emb, vs = app_and_services
        chunks = ["人工智能是计算机科学的分支，致力于创建智能系统。"]
        emb.fit_idf(chunks)
        embeddings = await emb.embed_batch(chunks)
        vs.add(1, "doc_test", chunks, embeddings)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/plugins/ddw-ent-knowledge/search",
                json={"query": "什么是人工智能", "top_k": 5},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["hits"]) >= 1
        assert isinstance(data["took_ms"], int)

    @pytest.mark.asyncio
    async def test_search_empty(self, app_and_services):
        app, emb, vs = app_and_services
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/plugins/ddw-ent-knowledge/search",
                json={"query": "不存在的内容", "top_k": 5},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["hits"] == []


# ---------------------------------------------------------------------------
# Chat SSE
# ---------------------------------------------------------------------------

class TestChatSSEEndpoint:
    @pytest.mark.asyncio
    async def test_chat_sse_format(self, app_and_services):
        """chat 返回 SSE 流：meta → token(s) → done，X-KB-Took-Ms 头存在。"""
        app, emb, vs = app_and_services
        chunks = ["DDW 平台是企业级 AI 底座，支持插件化扩展。"]
        emb.fit_idf(chunks)
        embeddings = await emb.embed_batch(chunks)
        vs.add(1, "doc_ddw", chunks, embeddings)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/plugins/ddw-ent-knowledge/chat",
                json={"query": "DDW 是什么", "top_k": 5},
            )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert "x-kb-took-ms" in resp.headers

        events = []
        for line in resp.text.strip().split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        assert len(events) >= 2
        assert events[0]["type"] == "meta"
        assert "kb_took_ms" in events[0]
        assert "hit_count" in events[0]
        token_events = [e for e in events if e["type"] == "token"]
        assert len(token_events) >= 1
        assert len(token_events[0]["token"]) > 0
        assert events[-1]["type"] == "done"

    @pytest.mark.asyncio
    async def test_chat_sse_no_hits(self, app_and_services):
        """无命中时 chat 仍返回完整 SSE 流。"""
        app, emb, vs = app_and_services
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/plugins/ddw-ent-knowledge/chat",
                json={"query": "完全无关的问题", "top_k": 5},
            )
        assert resp.status_code == 200
        events = []
        for line in resp.text.strip().split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
        assert events[-1]["type"] == "done"


# ---------------------------------------------------------------------------
# 上传组件（不走 HTTP，直接测 IngestService）
# ---------------------------------------------------------------------------

class TestUploadComponent:
    @pytest.mark.asyncio
    async def test_ingest_md(self, tmp_path):
        """md 文档入库：chunks 数量正确、文本完整。"""
        db_path = os.path.join(str(tmp_path), "vectors.sqlite")
        emb = SimpleEmbedding(dim=512)
        vs = VectorStore(db_path)
        ingest = IngestService(emb, vs, str(tmp_path))

        # 模拟 session（用 mock）
        from unittest.mock import AsyncMock, MagicMock

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.delete = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

        md_content = "# 产品介绍\n\nDDW 是企业级 AI 平台。\n\n## 技术架构\n\n基于微服务架构设计，支持高并发场景。"
        result = await ingest.ingest_upload(mock_session, 1, "intro.md", md_content.encode("utf-8"))

        assert result["status"] == "ready"
        assert result["chunk_count"] >= 1
        assert "doc_uuid" in result

    @pytest.mark.asyncio
    async def test_ingest_unsupported(self, tmp_path):
        """非法文件返回错误。"""
        db_path = os.path.join(str(tmp_path), "vectors.sqlite")
        emb = SimpleEmbedding(dim=512)
        vs = VectorStore(db_path)
        ingest = IngestService(emb, vs, str(tmp_path))

        from unittest.mock import AsyncMock, MagicMock

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        result = await ingest.ingest_upload(mock_session, 1, "test.docx", b"fake")
        assert result["status"] == "failed"
        assert "unsupported" in result["error"]
