from __future__ import annotations

"""ddw_transcript_ai 测试 conftest。

本插件**无 ORM 表**，不依赖任何外部插件模型。conftest 仅做：
- 注入 ``sys.path``（项目根）
- 提供 ``service`` fixture：直接构造 TranscriptService（带 echo backend LLM）
- 提供 ``client`` fixture：把 router 挂到 FastAPI + httpx.AsyncClient
"""

import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio

# 把项目根加入 sys.path
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@pytest_asyncio.fixture
async def llm():
    """Fresh EmbeddedLLM（echo backend，无外部依赖）。"""
    from plugins.embedded_llm.engine import EmbeddedLLM

    return EmbeddedLLM(knowledge_dir=None)


@pytest_asyncio.fixture
async def service(llm):
    """构造业务服务实例。"""
    from plugins.ddw_transcript_ai.services import TranscriptService

    return TranscriptService(llm)


@pytest_asyncio.fixture
async def client(service) -> AsyncIterator:
    """FastAPI TestClient（异步）：挂载本插件 router。"""
    import httpx
    from fastapi import FastAPI

    from plugins.ddw_transcript_ai.router import build_router

    app = FastAPI(title="ddw-transcript-ai-test")
    app.include_router(build_router(service))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
