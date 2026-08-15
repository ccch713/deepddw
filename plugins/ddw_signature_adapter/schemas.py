from __future__ import annotations

from typing import List, Optional

"""DDW 电子签章适配器插件 Pydantic schemas。

包含：
- SignatureRequestCreateReq  新建签署请求
- SignatureRequestUpdateReq  更新签署请求（仅 pending 状态可改）
- SignatureRequestResp       签署请求响应
- SignatureRequestListResp   分页列表响应
- SignatureRequestStatsResp  统计概览
- CallbackReq                第三方异步回调请求
- ManualUploadReq            人工上传签后文件请求
- SignerItem                 签署方信息（嵌套在 SignatureRequestCreateReq）
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 签署方条目
# ---------------------------------------------------------------------------


class SignerItem(BaseModel):
    """签署方信息。"""

    name: str = Field(..., min_length=1, max_length=100, description="签署方姓名")
    phone: Optional[str] = Field(None, max_length=20, description="签署方手机号")
    email: Optional[str] = Field(None, max_length=100, description="签署方邮箱")
    role: Optional[str] = Field(
        None, max_length=30, description="签署方角色（buyer/seller/witness/...）"
    )
    status: Optional[str] = Field(
        "pending", max_length=20, description="签署方状态（pending/signed/rejected）"
    )


# ---------------------------------------------------------------------------
# 创建
# ---------------------------------------------------------------------------


class SignatureRequestCreateReq(BaseModel):
    """新建签署请求。

    本版本不真正调用第三方 API —— 仅落库，状态默认 pending。
    后续可由后台 job / 手动触发器调用各 provider 适配器把 status 推进到 signing。
    """

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")

    contract_id: Optional[int] = Field(None, description="关联合同 ID（crm_contracts.id）")
    provider: str = Field(
        ...,
        min_length=1,
        max_length=30,
        description="电子签章服务商（tencent/dianxiaoyu/esign/manual）",
    )
    external_request_id: Optional[str] = Field(
        None, max_length=100, description="第三方系统返回的请求 ID（创建时一般为空）"
    )
    signers: Optional[List[SignerItem]] = Field(
        None, description="签署方列表（可空，使用时通过此字段记录各方信息）"
    )
    document_url: Optional[str] = Field(
        None, max_length=500, description="待签文件 URL"
    )
    notes: Optional[str] = None
    created_by: Optional[int] = Field(None, description="创建人 user_id")


# ---------------------------------------------------------------------------
# 更新（仅 pending 状态可改）
# ---------------------------------------------------------------------------


class SignatureRequestUpdateReq(BaseModel):
    """更新签署请求（仅 pending 状态可改）。"""

    provider: Optional[str] = Field(None, min_length=1, max_length=30)
    external_request_id: Optional[str] = Field(None, max_length=100)
    signers: Optional[List[SignerItem]] = None
    document_url: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# 第三方异步回调
# ---------------------------------------------------------------------------


class CallbackReq(BaseModel):
    """第三方异步回调请求体。

    当第三方签章服务完成签署（或失败 / 过期）时，异步回调到本端点。
    """

    status: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="目标状态：signed / rejected / expired",
    )
    signed_document_url: Optional[str] = Field(
        None, max_length=500, description="签后文件 URL（signed 时通常必填）"
    )
    external_request_id: Optional[str] = Field(
        None, max_length=100, description="第三方系统返回的请求 ID（用于关联）"
    )
    notes: Optional[str] = Field(None, description="附加说明")


# ---------------------------------------------------------------------------
# 人工上传签后文件
# ---------------------------------------------------------------------------


class ManualUploadReq(BaseModel):
    """人工上传签后文件请求体。

    当用户线下签完合同，可以手动把签后文件 URL 传上来。
    """

    signed_document_url: str = Field(
        ..., min_length=1, max_length=500, description="签后文件 URL"
    )
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------


class SignatureRequestResp(BaseModel):
    """签署请求响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int

    contract_id: Optional[int] = None
    provider: str
    external_request_id: Optional[str] = None
    signers: Optional[list] = None
    document_url: Optional[str] = None
    signed_document_url: Optional[str] = None
    status: str
    signed_at: Optional[datetime] = None
    notes: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[int] = None


class SignatureRequestListResp(BaseModel):
    """签署请求分页列表响应。"""

    total: int
    page: int
    page_size: int
    items: List[SignatureRequestResp]


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------


class SignatureRequestStatsResp(BaseModel):
    """签署请求统计概览。"""

    total: int
    pending: int
    signing: int
    signed: int
    rejected: int
    expired: int
    by_provider: dict[str, int]


__all__ = [
    "CallbackReq",
    "ManualUploadReq",
    "SignatureRequestCreateReq",
    "SignatureRequestListResp",
    "SignatureRequestResp",
    "SignatureRequestStatsResp",
    "SignatureRequestUpdateReq",
    "SignerItem",
]
