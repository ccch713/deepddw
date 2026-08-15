from __future__ import annotations

"""DDW 转写与结构化插件 Pydantic schemas。

包含：
- TranscribeReq/Resp：录音转写
- SummarizeReq/Resp：文本摘要
- ExtractTodosReq/Resp：待办提取
- ExtractEntitiesReq/Resp：实体抽取
"""

from typing import List

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 1. 转写
# ---------------------------------------------------------------------------


class TranscribeReq(BaseModel):
    """录音转写请求。

    - ``file_url``：必填，录音文件 URL
    - ``language``：可选，默认 ``zh-CN``
    """

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")
    file_url: str = Field(..., min_length=1, max_length=500, description="录音文件 URL（必填）")
    language: str = Field(
        "zh-CN",
        max_length=20,
        description="BCP-47 语言标签，默认 zh-CN",
    )


class TranscribeResp(BaseModel):
    """录音转写响应。"""

    file_url: str = Field(..., description="原始录音 URL（回传，便于上游关联）")
    language: str = Field(..., description="转写使用的语言")
    transcript: str = Field(..., description="转写文本")
    transcript_length: int = Field(..., ge=0, description="转写文本字符数")
    backend: str = Field(..., description="使用的 LLM backend 名称")
    model: str = Field(..., description="使用的 LLM 模型名称")


# ---------------------------------------------------------------------------
# 2. 摘要
# ---------------------------------------------------------------------------


class SummarizeReq(BaseModel):
    """文本摘要请求。"""

    tenant_id: int = Field(1, ge=1, description="租户 ID")
    text: str = Field(..., min_length=1, description="待摘要文本（必填）")
    max_length: int = Field(
        200,
        ge=20,
        le=2000,
        description="摘要最大字符数，默认 200，范围 20-2000",
    )


class SummarizeResp(BaseModel):
    """文本摘要响应。"""

    summary: str = Field(..., description="摘要文本")
    original_length: int = Field(..., ge=0, description="原文字符数")
    summary_length: int = Field(..., ge=0, description="摘要字符数")
    compression_ratio: float = Field(..., ge=0.0, le=1.0, description="压缩比 = summary/original")
    backend: str = Field(..., description="使用的 LLM backend 名称")
    model: str = Field(..., description="使用的 LLM 模型名称")


# ---------------------------------------------------------------------------
# 3. 待办提取
# ---------------------------------------------------------------------------


class ExtractTodosReq(BaseModel):
    """待办提取请求。"""

    tenant_id: int = Field(1, ge=1, description="租户 ID")
    text: str = Field(..., min_length=1, description="待提取的文本（必填）")


class ExtractTodosResp(BaseModel):
    """待办提取响应。"""

    todos: List[str] = Field(default_factory=list, description="提取出的待办事项列表")
    count: int = Field(0, ge=0, description="待办条目数")
    backend: str = Field(..., description="使用的 LLM backend 名称")
    model: str = Field(..., description="使用的 LLM 模型名称")


# ---------------------------------------------------------------------------
# 4. 实体抽取
# ---------------------------------------------------------------------------


class ExtractEntitiesReq(BaseModel):
    """关键实体抽取请求。"""

    tenant_id: int = Field(1, ge=1, description="租户 ID")
    text: str = Field(..., min_length=1, description="待抽取的文本（必填）")


class ExtractEntitiesResp(BaseModel):
    """关键实体抽取响应。

    四类实体（公司/人物/金额/日期）都允许为空列表。
    """

    companies: List[str] = Field(default_factory=list, description="公司/机构名")
    people: List[str] = Field(default_factory=list, description="人名")
    amounts: List[str] = Field(default_factory=list, description="金额（保留原始写法，如'30万'）")
    dates: List[str] = Field(default_factory=list, description="日期（保留原始写法，如'2026-08-15'）")
    total_count: int = Field(0, ge=0, description="四类实体总数")
    backend: str = Field(..., description="使用的 LLM backend 名称")
    model: str = Field(..., description="使用的 LLM 模型名称")


__all__ = [
    "ExtractEntitiesReq",
    "ExtractEntitiesResp",
    "ExtractTodosReq",
    "ExtractTodosResp",
    "SummarizeReq",
    "SummarizeResp",
    "TranscribeReq",
    "TranscribeResp",
]

