from __future__ import annotations

from typing import List, Optional

"""DDW 录音与语音输入插件 Pydantic schemas。

包含：
- VoiceRecordCreateReq：上传录音元数据请求（file_url / file_size / duration_seconds 必填）
- VoiceRecordResp：录音响应
- VoiceRecordListResp：分页列表
- VoiceRecordStatsResp：统计概览
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 创建
# ---------------------------------------------------------------------------


class VoiceRecordCreateReq(BaseModel):
    """上传录音元数据请求。

    - 必填：file_url / file_size / duration_seconds
    - 选填：company_id / contact_id / opportunity_id / source_type / notes
    - source_type 枚举：local / phone / meeting / memo
    - status 由本服务默认 ``uploaded``，调用方不传
    """

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")

    user_id: Optional[int] = Field(None, ge=1, description="上传用户 ID（销售/客户经理）")
    company_id: Optional[int] = Field(None, ge=1, description="关联企业 ID（crm_companies.id）")
    contact_id: Optional[int] = Field(None, ge=1, description="关联联系人 ID（crm_contacts.id）")
    opportunity_id: Optional[int] = Field(
        None, ge=1, description="关联商机 ID（crm_opportunities.id）"
    )

    file_url: str = Field(..., min_length=1, max_length=500, description="录音文件 URL（必填）")
    file_size: int = Field(..., ge=0, description="文件字节数（必填，>=0）")
    duration_seconds: int = Field(..., ge=0, description="录音时长，秒（必填，>=0）")

    source_type: Optional[str] = Field(
        None,
        max_length=30,
        description="录音来源：local / phone / meeting / memo",
    )
    notes: Optional[str] = Field(None, description="备注")

    created_by: Optional[int] = Field(None, description="创建人 ID")


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------


class VoiceRecordResp(BaseModel):
    """录音响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int

    user_id: Optional[int] = None
    company_id: Optional[int] = None
    contact_id: Optional[int] = None
    opportunity_id: Optional[int] = None

    file_url: Optional[str] = None
    file_size: Optional[int] = None
    duration_seconds: Optional[int] = None

    source_type: Optional[str] = None
    notes: Optional[str] = None
    status: str

    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    # 录音不可修改，故不暴露 updated_at


class VoiceRecordListResp(BaseModel):
    """录音分页列表响应。"""

    total: int
    page: int
    page_size: int
    items: List[VoiceRecordResp]


class VoiceRecordStatsResp(BaseModel):
    """录音统计概览。

    - 各状态计数（total / uploaded / transcribed / processed / failed）
    - 总录音时长 total_duration（秒，所有记录 duration_seconds 之和）
    - 总文件大小 total_size（字节，所有记录 file_size 之和）
    - 按 source_type 分组计数
    """

    total: int
    uploaded: int
    transcribed: int
    processed: int
    failed: int
    total_duration: int = Field(0, description="所有录音时长之和（秒）")
    total_size: int = Field(0, description="所有录音文件大小之和（字节）")
    by_source_type: dict[str, int] = Field(
        default_factory=dict, description="按 source_type 分组计数"
    )


__all__ = [
    "VoiceRecordCreateReq",
    "VoiceRecordListResp",
    "VoiceRecordResp",
    "VoiceRecordStatsResp",
]
