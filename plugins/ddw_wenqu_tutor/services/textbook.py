"""教材 PDF 加载/OCR/切片/入库。"""
from __future__ import annotations

import time
import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wenqu_tutor.models import (
    WenquTextbook,
    WenquTextbookChunk,
)


def generate_textbook_id() -> str:
    """生成教材 ID。"""
    return f"T{int(time.time() * 1000)}{uuid.uuid4().hex[:6]}"


def estimate_tokens(text: str) -> int:
    """估算 token 数：CJK=1，非CJK=0.25。"""
    import re

    cjk_re = re.compile(
        r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]"
    )
    cjk_count = len(cjk_re.findall(text))
    non_cjk = len(text) - cjk_count
    return cjk_count + int(non_cjk * 0.25)


async def list_textbooks(
    db: AsyncSession,
    subject: Optional[str] = None,
) -> list[WenquTextbook]:
    """查询教材列表。"""
    query = select(WenquTextbook)
    if subject:
        query = query.where(
            WenquTextbook.subject == subject
        )
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_textbook(
    db: AsyncSession, textbook_id: str
) -> Optional[WenquTextbook]:
    """获取单个教材。"""
    result = await db.execute(
        select(WenquTextbook).where(
            WenquTextbook.id == textbook_id
        )
    )
    return result.scalar_one_or_none()


async def register_textbook(
    db: AsyncSession,
    subject: str,
    grade: str,
    version: str,
    file_path: str,
    chapters: list[dict],
) -> WenquTextbook:
    """注册教材（不包含 OCR 切片）。"""
    import json

    textbook = WenquTextbook(
        id=generate_textbook_id(),
        subject=subject,
        grade=grade,
        version=version,
        file_path=file_path,
        chapters=json.dumps(chapters, ensure_ascii=False),
        indexed_at=None,
    )
    db.add(textbook)
    await db.commit()
    return textbook


async def index_textbook(
    db: AsyncSession,
    textbook_id: str,
    chunks: list[dict],
) -> int:
    """切片入库。

    Args:
        chunks: list of {chapter, page_range, content}

    Returns:
        切片数量
    """
    count = 0
    for chunk in chunks:
        token_count = estimate_tokens(chunk["content"])
        db.add(
            WenquTextbookChunk(
                textbook_id=textbook_id,
                chapter=chunk["chapter"],
                page_range=chunk["page_range"],
                content=chunk["content"],
                token_count=token_count,
            )
        )
        count += 1

    # 更新教材索引时间
    from sqlalchemy import update

    await db.execute(
        update(WenquTextbook)
        .where(WenquTextbook.id == textbook_id)
        .values(
            indexed_at=func.now()
        )  # noqa: F821
    )
    await db.commit()
    return count


async def query_textbook_chunks(
    db: AsyncSession,
    textbook_id: str,
    chapter: Optional[str] = None,
    max_tokens: int = 4000,
) -> list[WenquTextbookChunk]:
    """查询教材切片（按 token 预算截断）。"""
    query = select(WenquTextbookChunk).where(
        WenquTextbookChunk.textbook_id == textbook_id
    )
    if chapter:
        query = query.where(
            WenquTextbookChunk.chapter == chapter
        )
    query = query.order_by(WenquTextbookChunk.id)

    result = await db.execute(query)
    chunks = list(result.scalars().all())

    # 按 token 预算截断
    selected = []
    total_tokens = 0
    for chunk in chunks:
        if (
            total_tokens + chunk.token_count
            > max_tokens
        ):
            break
        selected.append(chunk)
        total_tokens += chunk.token_count

    return selected


def ocr_pdf(file_path: str) -> list[dict]:
    """本地 OCR（PaddleOCR/Tesseract）。

    Returns:
        list of {page, text}
    """
    # TODO: 实现本地 OCR
    # 这里是占位实现
    return [{"page": 1, "text": "OCR 待实现"}]


def split_into_chapters(
    pages: list[dict],
) -> list[dict]:
    """按章节切片。

    Returns:
        list of {chapter, page_range, content}
    """
    # TODO: 实现章节识别和切片
    # 这里是简单实现
    if not pages:
        return []

    content = "\n".join(
        p.get("text", "") for p in pages
    )
    return [
        {
            "chapter": "第一章",
            "page_range": f"1-{len(pages)}",
            "content": content,
        }
    ]


__all__ = [
    "get_textbook",
    "index_textbook",
    "list_textbooks",
    "ocr_pdf",
    "query_textbook_chunks",
    "register_textbook",
    "split_into_chapters",
]
