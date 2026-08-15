"""ddw_docs_portal 测试夹具。

策略（TASK_SPEC 第七节：mock 依赖，不碰真实服务）：
- in-memory SQLite（StaticPool）+ Base.metadata.create_all
- monkeypatch services._get_da_service → FakeDocAssistant（ingest/chunks/query）
- monkeypatch services._get_memory_service → FakeMemoryService（create/update 计数）
- HTTP 层：轻量 FastAPI app 仅挂 build_router()，monkeypatch session maker 指向内存库
"""
from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio

os.environ.setdefault("DDW_JWT_SECRET", "test-secret-docs-portal")
os.environ.setdefault("DDW_ALWAYS_ACCEPT_CODE", "8888")

# 平台根目录入 sys.path（独立跑插件测试时）
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.auth.jwt import create_access_token
from core.database.session import Base, session_scope
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# 触发 docs_* 三张表注册到 Base.metadata（含 core Tenant/User 等依赖表）
from plugins.ddw_docs_portal import models as _portal_models  # noqa: F401
from plugins.ddw_docs_portal.services import DocsPortalService

# ─── 用户上下文（current_user 返回结构） ────────────────────────

SUPERADMIN = {"user_id": 1, "tenant_id": 1, "role": "superadmin"}
TENANT_ADMIN = {"user_id": 5, "tenant_id": 1, "role": "owner"}
MEMBER_A = {"user_id": 10, "tenant_id": 1, "role": "member"}
MEMBER_B = {"user_id": 11, "tenant_id": 2, "role": "member"}


# ─── fake 依赖 ─────────────────────────────────────────────────


class FakeDocAssistant:
    """mock ddw_doc_assistant：ingest 返回自增 doc_id，chunks 记录原文。"""

    def __init__(self) -> None:
        self.ingested = 0
        self.chunks_by_doc: dict = {}
        self.query_result = {
            "answer": "基于知识库检索，找到 1 条相关内容",
            "sources": [
                {
                    "chunk_id": "c1",
                    "doc_id": "da-1",
                    "doc_title": "测试文档",
                    "content": "DDW 部署需要 3 天",
                    "score": 0.9,
                    "chunk_index": 0,
                }
            ],
            "doc_ids_queried": ["da-1"],
        }

    async def ingest_document(
        self, file_path, *, title=None, uploader="", department="", tenant_id=0
    ):
        self.ingested += 1
        doc_id = f"da-{self.ingested}"
        self.chunks_by_doc[doc_id] = [{"content": file_path.read_text(encoding="utf-8")}]
        return SimpleNamespace(id=doc_id, title=title or "未命名")

    async def get_document_chunks(self, doc_id):
        return [{"content": c["content"]} for c in self.chunks_by_doc.get(doc_id, [])]

    async def query(self, question, *, doc_ids=None, top_k=5, tenant_id=0):
        return self.query_result


class FakeMemoryService:
    """mock ddw_memory：create/update 计数 + 内存条目（验证 upsert 只一条）。"""

    def __init__(self) -> None:
        self.created = 0
        self.updated = 0
        self.items: list = []

    async def list_memories(self, tenant_id, layer=None, page_size=20):
        return {"items": list(self.items), "total": len(self.items)}

    async def create_memory(self, tenant_id, layer, content, creator_id, tags=None, **kwargs):
        self.created += 1
        entry = SimpleNamespace(id=self.created, tags=list(tags or []), content=content)
        self.items.append(entry)
        return entry

    async def update_memory(self, tenant_id, memory_id, content=None, tags=None, **kwargs):
        self.updated += 1
        for entry in self.items:
            if entry.id == memory_id:
                if content is not None:
                    entry.content = content
                if tags is not None:
                    entry.tags = tags
        return SimpleNamespace(id=memory_id)


# ─── fixtures ──────────────────────────────────────────────────


@pytest_asyncio.fixture
async def engine() -> AsyncIterator:
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def patch_session(monkeypatch, engine):
    """把平台 session maker 指向内存库（session_scope 生效）。"""

    def _patch():
        from core.database import session as db_session

        maker = async_sessionmaker(
            bind=engine, expire_on_commit=False, class_=AsyncSession
        )
        monkeypatch.setattr(db_session, "_session_maker", maker)
        monkeypatch.setattr(db_session, "_engine", engine)
        return maker

    return _patch


@pytest_asyncio.fixture
async def service(engine, patch_session, fake_da, fake_memory) -> DocsPortalService:
    """业务服务（内存库 + fake 依赖）。"""
    patch_session()
    async with session_scope() as db:
        yield DocsPortalService(db)


@pytest.fixture
def fake_da(monkeypatch):
    fake = FakeDocAssistant()
    monkeypatch.setattr(
        "plugins.ddw_docs_portal.services._get_da_service", lambda db: fake
    )
    return fake


@pytest.fixture
def fake_memory(monkeypatch):
    fake = FakeMemoryService()
    monkeypatch.setattr(
        "plugins.ddw_docs_portal.services._get_memory_service", lambda: fake
    )
    return fake


@pytest_asyncio.fixture
async def client(engine, patch_session, fake_da, fake_memory):
    """HTTP 客户端：仅挂载本插件 router（轻量，不加载全平台）。"""
    import httpx
    from fastapi import FastAPI
    from httpx import ASGITransport

    from plugins.ddw_docs_portal.router import build_router

    patch_session()
    app = FastAPI()
    app.include_router(build_router())
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def token_superadmin() -> str:
    return create_access_token(user_id=1, tenant_id=1, role="superadmin")


@pytest.fixture
def auth_headers(token_superadmin) -> dict:
    return {"Authorization": f"Bearer {token_superadmin}"}
