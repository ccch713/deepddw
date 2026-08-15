"""文档分块：按标题/段落切块，800-1500 字符。"""

from __future__ import annotations

import re
from typing import List, Tuple

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_PARA_SPLIT = re.compile(r"\n\s*\n")


def chunk_text(text: str, target_size: int = 800, max_size: int = 1500) -> List[str]:
    """智能分块：按二级标题优先，单块控制在 target_size 字以内。"""
    if not text or not text.strip():
        return []

    # 1. 按二级标题切
    sections: List[Tuple[str, str]] = []
    current_h = ""
    current_body: List[str] = []
    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m and len(m.group(1)) <= 2:
            if current_body or current_h:
                sections.append((current_h, "\n".join(current_body).strip()))
            current_h = m.group(2).strip()
            current_body = []
        else:
            current_body.append(line)
    if current_body or current_h:
        sections.append((current_h, "\n".join(current_body).strip()))

    # 2. 每段内部按段落切，合并到 target_size
    chunks: List[str] = []
    for heading, body in sections:
        if not body and not heading:
            continue
        full = f"## {heading}\n{body}".strip() if heading else body
        if len(full) <= max_size:
            chunks.append(full)
            continue
        paras = [p.strip() for p in _PARA_SPLIT.split(body) if p.strip()]
        buf: List[str] = []
        cur_len = len(heading) + 4
        prefix = f"## {heading}\n" if heading else ""
        for p in paras:
            if cur_len + len(p) > target_size and buf:
                chunks.append(prefix + "\n".join(buf))
                buf = [p]
                cur_len = len(prefix) + len(p)
            else:
                buf.append(p)
                cur_len += len(p) + 2
        if buf:
            chunks.append(prefix + "\n".join(buf))

    return [c for c in chunks if c.strip() and len(c.strip()) >= 20]


__all__ = ["chunk_text"]
