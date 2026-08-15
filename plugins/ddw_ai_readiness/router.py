"""ddw_ai_readiness API 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from core.auth.jwt import current_user

from .schemas import StatsOut, SubmissionDetail, SubmissionIn, SubmissionOut
from .services import (
    get_stats,
    get_submission,
    list_submissions,
    save_submission,
    score_submission,
)

router = APIRouter(prefix="/api/v1/plugins/ddw_ai_readiness", tags=["ddw_ai_readiness"])


def build_router() -> APIRouter:
    @router.post("/submissions", response_model=SubmissionOut)
    async def submit(payload: SubmissionIn):
        """提交测评（匿名可提交，供客户自助入口调用）。"""
        try:
            scores = score_submission(payload.model_dump())
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        sid = save_submission(payload.model_dump(), scores)
        return SubmissionOut(id=sid, created_at="", **scores)

    @router.get("/submissions", response_model=list[SubmissionDetail])
    async def list_all(
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        _user: dict = Depends(current_user),
    ):
        """销售端列表（内部使用，需登录）。"""
        return list_submissions(limit, offset)

    @router.get("/submissions/{sid}", response_model=SubmissionDetail)
    async def detail(
        sid: int,
        _user: dict = Depends(current_user),
    ):
        """销售端详情（需登录）。"""
        row = get_submission(sid)
        if not row:
            raise HTTPException(status_code=404, detail="submission not found")
        return row

    @router.get("/stats", response_model=StatsOut)
    async def stats(
        _user: dict = Depends(current_user),
    ):
        """统计数据（内部使用，需登录，商机数据不公开）。"""
        return get_stats()

    @router.get("/health")
    async def health():
        """健康检查（匿名可访问）。"""
        return {"plugin": "ddw_ai_readiness", "version": "0.1.0", "status": "ok"}

    return router


__all__ = ["build_router"]
