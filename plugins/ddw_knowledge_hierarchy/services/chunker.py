"""文档分块器：按层级结构分割文档为 chunk。

策略：
1. 优先按文档自然段落边界分割
2. 段落超过 chunk_size 时按句子边界分割
3. 每个 chunk 记录其 tree_node_id，保持层级关联
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 800  # tokens (approx chars / 1.5 for Chinese)
DEFAULT_CHUNK_OVERLAP = 100


@dataclass
class Chunk:
    """单个文档分块。"""
    content: str
    chunk_index: int
    content_hash: str
    token_count: int
    page_number: Optional[int] = None
    is_table: bool = False
    is_figure: bool = False
    section_title: str = ""
    section_path: str = ""  # "章 > 节 > 小节"


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数（中文约 1.5 字/token，英文约 4 字符/token）。"""
    cn_chars = len(re.findall(r"[\u4e00-\u9fa5]", text))
    en_chars = len(text) - cn_chars
    return int(cn_chars / 1.5 + en_chars / 4)


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    section_title: str = "",
    section_path: str = "",
    page_number: Optional[int] = None,
) -> List[Chunk]:
    """将文本分割为 chunk。"""
    if not text or not text.strip():
        return []

    # 按段落分割
    paragraphs = re.split(r"\n\s*\n", text)
    chunks: List[Chunk] = []
    current_text = ""
    chunk_idx = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        para_tokens = estimate_tokens(para)

        # 如果单个段落就超了，按句子拆
        if para_tokens > chunk_size:
            # 先保存当前累积的
            if current_text:
                chunks.append(_make_chunk(current_text, chunk_idx, section_title, section_path, page_number))
                chunk_idx += 1
                current_text = ""

            # 按句子拆分大段落
            sentences = re.split(r"([。！？；\n])", para)
            buf = ""
            for i in range(0, len(sentences), 2):
                sent = sentences[i]
                sep = sentences[i + 1] if i + 1 < len(sentences) else ""
                candidate = buf + sent + sep
                if estimate_tokens(candidate) > chunk_size and buf:
                    chunks.append(_make_chunk(buf, chunk_idx, section_title, section_path, page_number))
                    chunk_idx += 1
                    # overlap
                    buf = candidate[-chunk_overlap * 2:] if len(candidate) > chunk_overlap * 2 else candidate
                else:
                    buf = candidate
            if buf:
                current_text = buf
            continue

        # 正常累积
        candidate = (current_text + "\n\n" + para).strip() if current_text else para
        if estimate_tokens(candidate) > chunk_size and current_text:
            chunks.append(_make_chunk(current_text, chunk_idx, section_title, section_path, page_number))
            chunk_idx += 1
            # overlap: 取上一个 chunk 的尾部
            overlap_text = current_text[-chunk_overlap * 2:] if len(current_text) > chunk_overlap * 2 else current_text
            current_text = (overlap_text + "\n\n" + para).strip()
        else:
            current_text = candidate

    # 最后一块
    if current_text:
        chunks.append(_make_chunk(current_text, chunk_idx, section_title, section_path, page_number))

    return chunks


def _make_chunk(
    text: str, index: int, section_title: str, section_path: str,
    page_number: Optional[int],
) -> Chunk:
    return Chunk(
        content=text.strip(),
        chunk_index=index,
        content_hash=hashlib.sha256(text.strip().encode()).hexdigest(),
        token_count=estimate_tokens(text),
        section_title=section_title,
        section_path=section_path,
        page_number=page_number,
    )
