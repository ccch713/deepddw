"""知识检索：基于项目类型 + 关键词 + 数值范围的混合打分。"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_cost_knowledge.models import CostDocument

logger = logging.getLogger(__name__)


class SearchService:
    """轻量级检索（不依赖向量库）。生产可替换为 RAG 检索。"""

    def __init__(self, max_results: int = 20) -> None:
        self.max_results = max_results

    async def search(
        self,
        session: AsyncSession,
        query: str,
        project_type: Optional[str] = None,
        doc_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """自然语言检索：分词 + 多字段打分排序。"""
        tokens = self._tokenize(query)
        where = []
        if project_type:
            where.append(CostDocument.project_type == project_type)
        if doc_type:
            where.append(CostDocument.doc_type == doc_type)
        q = select(CostDocument)
        if where:
            from sqlalchemy import and_

            q = q.where(and_(*where))
        rows = (await session.execute(q)).scalars().all()

        scored: List[Tuple[float, CostDocument, str]] = []
        for r in rows:
            score, snippet = self._score(r, tokens)
            if score > 0:
                scored.append((score, r, snippet))

        scored.sort(key=lambda x: -x[0])
        n = limit or self.max_results
        return [
            {
                "document_id": r.id,
                "file_name": r.file_name,
                "doc_type": r.doc_type,
                "project_name": r.project_name,
                "project_type": r.project_type,
                "total_cost": r.total_cost,
                "area": r.area,
                "unit_price": r.unit_price,
                "score": round(score, 3),
                "snippet": snippet,
            }
            for score, r, snippet in scored[:n]
        ]

    # ----------------- 内部 ----------------- #

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """简单中英文分词：英文按空格，中文按字符 + 二元。"""
        if not text:
            return []
        text = text.lower()
        # 英文/数字 token
        en_tokens = re.findall(r"[a-z0-9]+", text)
        # 中文字符 token
        zh_chars = re.findall(r"[\u4e00-\u9fa5]", text)
        # 中文 bigram
        bigrams = [zh_chars[i] + zh_chars[i + 1] for i in range(len(zh_chars) - 1)]
        return en_tokens + zh_chars + bigrams

    def _score(self, doc: CostDocument, tokens: List[str]) -> Tuple[float, str]:
        if not tokens:
            return 0.0, ""
        # 把 doc 拼成可搜文本
        haystack_parts = [
            doc.file_name or "",
            doc.project_name or "",
            doc.project_type or "",
            doc.doc_type or "",
            doc.notes or "",
        ]
        if isinstance(doc.extracted_data, dict):
            haystack_parts.append(str(doc.extracted_data.get("file_keywords", "")))
        haystack = " ".join(haystack_parts).lower()
        if not haystack.strip():
            return 0.0, ""

        score = 0.0
        hit_count = 0
        snippet_terms: List[str] = []
        for tok in tokens:
            count = haystack.count(tok)
            if count > 0:
                # bigram 权重低一些
                w = 0.5 if len(tok) == 2 and any("\u4e00" <= c <= "\u9fa5" for c in tok) else 1.0
                score += count * w
                hit_count += 1
                snippet_terms.append(tok)
        if score == 0:
            return 0.0, ""
        # 归一化：除以 token 总数
        score = score / max(1, len(tokens))
        snippet = (
            f"命中关键词：{', '.join(snippet_terms[:6])}"
            + (f" · 项目：{doc.project_name}" if doc.project_name else "")
        )
        return score, snippet


__all__ = ["SearchService"]
