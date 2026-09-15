"""P0/P1：无痕会话开关 + 检索健康可观测 + 注入预览。

对应社区痛点：
- mneme #47 无痕模式
- mneme #179 / kb-rag #2 / mneme #188：看不见注入、静默降级
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core.api_response import fail, ok
from core.privacy import privacy_status, reset_privacy_map, set_incognito
from core.security.token_gate import require_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/privacy", tags=["privacy", "retrieval-health"])

_health_lock_notes: Dict[str, Any] = {}


class IncognitoReq(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    enabled: bool = True


@router.post("/incognito")
async def incognito_endpoint(
    payload: IncognitoReq,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """开启/关闭会话无痕：本会话不写记忆（读保持默认）。"""
    result = set_incognito(payload.session_id, payload.enabled)
    if not result.get("ok"):
        return fail(result.get("note", "failed"))
    return ok(result)


@router.get("/status")
async def status_endpoint(
    session_id: Optional[str] = None,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    return ok(privacy_status(session_id))


@router.post("/reset")
async def reset_endpoint(
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    reset_privacy_map()
    return ok({"ok": True})


# ---------------------------------------------------------------------------
# 检索健康（P1-4）
# ---------------------------------------------------------------------------


@router.get("/retrieval-health")
async def retrieval_health(
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """FTS / LanceDB / 记忆表健康探针——失败显式上报，禁止静默。"""
    from core import knowledge as kb

    report: Dict[str, Any] = {
        "ok": True,
        "checked_at": time.time(),
        "checks": {},
        "warnings": [],
    }

    # FTS
    try:
        conn = kb.get_conn()
        try:
            fts = kb._fts_supported(conn)
            report["checks"]["fts5"] = {"available": bool(fts)}
            if not fts:
                report["warnings"].append("FTS5 unavailable; kb_search falls back to LIKE")
        finally:
            kb.close_conn(conn)
    except Exception as exc:  # noqa: BLE001
        report["ok"] = False
        report["checks"]["fts5"] = {"available": False, "error": str(exc)}
        report["warnings"].append(f"FTS probe failed: {exc}")

    # LanceDB / 向量
    try:
        lance = kb._vector_available() if hasattr(kb, "_vector_available") else None
        if lance is None:
            # 探测：LANCEDB_PATH 或默认路径存在则视为可能启用
            lance = bool(os.environ.get("LANCEDB_PATH") or os.environ.get("DDW_LANCEDB_PATH"))
        report["checks"]["lancedb"] = {
            "configured": bool(lance),
            "note": "vector search degrades to keyword-only when unavailable",
        }
        if not lance:
            report["warnings"].append("LanceDB not configured; hybrid retrieval is keyword-only")
    except Exception as exc:  # noqa: BLE001
        report["checks"]["lancedb"] = {"configured": False, "error": str(exc)}

    # 关键词扩写缓存
    try:
        report["checks"]["keyword_cache"] = {
            "size": len(getattr(kb, "_keyword_cache", {}) or {}),
        }
    except Exception:  # noqa: BLE001
        pass

    # 模拟一次空查询 kb_search 探活（不写库）
    try:
        probe = kb.kb_search("__health_probe__", top_k=1)
        report["checks"]["kb_search"] = {
            "degraded": bool(probe.get("degraded")),
            "mode": probe.get("mode"),
            "note": probe.get("note"),
        }
        if probe.get("degraded"):
            report["warnings"].append(f"kb_search degraded: {probe.get('note')}")
            report["ok"] = False
    except Exception as exc:  # noqa: BLE001
        report["ok"] = False
        report["checks"]["kb_search"] = {"error": str(exc)}
        report["warnings"].append(str(exc))

    return ok(report)


@router.get("/injection-preview")
async def injection_preview(
    workspace: str = "shared",
    budget: int = 2400,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """预览当前 workspace 将注入对话的记忆块（可观测，不改数据）。"""
    from core.knowledge import memory_context_build

    mem = memory_context_build(budget=budget, workspace=workspace)
    ctx = mem.get("context") or ""
    return ok({
        "workspace": workspace,
        "chars": mem.get("chars", len(ctx)),
        "degraded": bool(mem.get("degraded")),
        "preview": ctx[:4000],
        "truncated": len(ctx) > 4000,
        "sections": mem.get("sections") if isinstance(mem.get("sections"), (dict, list)) else None,
    })
