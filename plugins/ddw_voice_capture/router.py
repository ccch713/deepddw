from __future__ import annotations

from typing import Optional

"""DDW 录音与语音输入插件 API 路由。

API 端点（6 个）：
  健康检查：GET  /health
  上传元数据：POST /voice-records
  列表      ：GET  /voice-records
  详情      ：GET  /voice-records/{id}
  软删除    ：DELETE /voice-records/{id}
  统计      ：GET  /voice-records/stats
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .schemas import (
    VoiceRecordCreateReq,
    VoiceRecordListResp,
    VoiceRecordStatsResp,
)
from .services import VoiceRecordService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造录音与语音输入路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-voice-capture",
        tags=["ddw-voice-capture"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-voice-capture", "version": "1.0.0", "status": "ok"}

    # -----------------------------------------------------------------------
    # 上传录音元数据
    # -----------------------------------------------------------------------
    @router.post("/voice-records", response_model=dict, status_code=201)
    async def create_voice_record(data: VoiceRecordCreateReq) -> dict:
        """上传录音元数据。

        - ``file_url / file_size / duration_seconds`` 必填
        - 关联字段（``company_id / contact_id / opportunity_id``）皆可选
        - 状态默认 ``uploaded``，由 P3-3 转写完成后更新为 ``transcribed / processed``
        """
        async with session_scope() as db, bypass_tenant_filter():
            svc = VoiceRecordService(db)
            return await svc.create(data)

    # -----------------------------------------------------------------------
    # 列表（分页 + 多维筛选）
    # -----------------------------------------------------------------------
    @router.get("/voice-records", response_model=VoiceRecordListResp)
    async def list_voice_records(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页条数"),
        user_id: Optional[int] = Query(None, description="按上传用户 ID 筛选"),
        company_id: Optional[int] = Query(None, description="按关联企业 ID 筛选"),
        contact_id: Optional[int] = Query(None, description="按关联联系人 ID 筛选"),
        opportunity_id: Optional[int] = Query(
            None, description="按关联商机 ID 筛选"
        ),
        source_type: Optional[str] = Query(
            None, description="按来源筛选（local/phone/meeting/memo）"
        ),
        status: Optional[str] = Query(
            None, description="按状态筛选（uploaded/transcribed/processed/failed）"
        ),
    ) -> VoiceRecordListResp:
        """录音列表（分页 + 多维筛选）。

        支持的筛选维度：上传人、关联企业/联系人/商机、来源、状态。
        """
        async with session_scope() as db, bypass_tenant_filter():
            svc = VoiceRecordService(db)
            return await svc.list(
                page=page,
                page_size=page_size,
                user_id=user_id,
                company_id=company_id,
                contact_id=contact_id,
                opportunity_id=opportunity_id,
                source_type=source_type,
                status=status,
            )

    # -----------------------------------------------------------------------
    # 统计
    # -----------------------------------------------------------------------
    @router.get("/voice-records/stats", response_model=VoiceRecordStatsResp)
    async def voice_record_stats() -> VoiceRecordStatsResp:
        """录音统计概览。

        - 各状态计数（total / uploaded / transcribed / processed / failed）
        - 总录音时长（秒）
        - 总文件大小（字节）
        - 按 source_type 分组计数
        """
        async with session_scope() as db, bypass_tenant_filter():
            svc = VoiceRecordService(db)
            return await svc.stats()

    # -----------------------------------------------------------------------
    # 详情
    # -----------------------------------------------------------------------
    @router.get("/voice-records/{record_id}", response_model=dict)
    async def get_voice_record(record_id: int) -> dict:
        """录音详情。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = VoiceRecordService(db)
            result = await svc.get(record_id)
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"voice record {record_id} not found",
                )
            return result

    # -----------------------------------------------------------------------
    # 软删除
    # -----------------------------------------------------------------------
    @router.delete("/voice-records/{record_id}", response_model=dict)
    async def delete_voice_record(record_id: int) -> dict:
        """软删除录音（``status=failed`` + ``notes`` 追加 ``"deleted by user"``）。

        录音属于历史资产，**不物理删除**。
        """
        async with session_scope() as db, bypass_tenant_filter():
            svc = VoiceRecordService(db)
            result = await svc.soft_delete(record_id)
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"voice record {record_id} not found or already deleted",
                )
            return result

    return router


__all__ = ["build_router"]
