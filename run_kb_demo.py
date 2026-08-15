"""DDW 知识库引擎演示服务（独立启动，SQLite，无平台依赖）

用法：python3 run_kb_demo.py   →  http://0.0.0.0:8001
演示页：http://localhost:8001/static/kb_demo.html （或插件 templates/kb_demo.html）
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import uvicorn
from fastapi import FastAPI

from core.database.session import Base, get_engine
from plugins.ddw_ent_knowledge import models  # noqa: F401  注册 ORM 表
from plugins.ddw_ent_knowledge.router import router as kb_router

app = FastAPI(title="DDW 知识库演示服务", version="0.1.0")
app.include_router(kb_router)


@app.on_event("startup")
async def startup() -> None:
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print(">>> KB tables ready (sqlite)")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
