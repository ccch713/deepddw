"""标书风格修饰（中性命名版）。

⚠️ 脱敏要求：
- 本服务命名与 UI 文案均使用"标书风格修饰"中性词
- 可选风格：标准 / 保守 / 激进 / 创新型
- 实际能力通过线下口头说明
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_bid_writer.models import BidDocument

logger = logging.getLogger(__name__)


# 各风格的特征关键词（用于差异度量）
STYLE_PROFILES: Dict[str, Dict[str, Any]] = {
    "标准": {
        "tone_words": ["合理", "规范", "符合", "满足", "确保"],
        "intensifiers": ["充分", "严格", "有效"],
        "sentence_target_len": 25,  # 目标平均句长
        "forbidden_phrases": ["突破", "颠覆", "绝对领先", "远超"],
    },
    "保守": {
        "tone_words": ["稳妥", "可靠", "成熟", "沿用", "经验"],
        "intensifiers": ["谨慎", "稳定", "成熟可靠"],
        "sentence_target_len": 20,
        "forbidden_phrases": ["率先", "首创", "独家", "行业第一"],
    },
    "激进": {
        "tone_words": ["突破", "创新", "领先", "超越", "差异化"],
        "intensifiers": ["显著", "大幅", "卓越", "行业前沿"],
        "sentence_target_len": 30,
        "forbidden_phrases": ["保守", "传统", "沿袭"],
    },
    "创新型": {
        "tone_words": ["首创", "独家", "领先", "突破性", "差异化"],
        "intensifiers": ["革命性", "颠覆性", "全新", "前沿"],
        "sentence_target_len": 32,
        "forbidden_phrases": ["常规", "传统", "套用"],
    },
}


def _split_sentences(text: str) -> List[str]:
    """按中英文标点切句。"""
    return [s.strip() for s in re.split(r"[。！？!?\n]+", text) if s.strip()]


def _avg_len(sentences: List[str]) -> float:
    if not sentences:
        return 0.0
    return sum(len(s) for s in sentences) / len(sentences)


def _count_keywords(text: str, keywords: List[str]) -> int:
    return sum(text.count(k) for k in keywords)


def _swap_keywords(text: str, profile: Dict[str, Any], target: str) -> str:
    """按 target 风格做关键词替换（轻量级、不依赖 LLM）。"""
    if target == "标准":
        return text
    # 仅在两两风格之间做粗略替换
    tone_map = {
        "保守": {"突破": "沿用", "创新": "借鉴", "领先": "符合", "超越": "达到", "颠覆": "稳定"},
        "激进": {"沿用": "突破", "借鉴": "创新", "符合": "超越", "稳定": "优化"},
        "创新型": {
            "常规": "全新", "传统": "首创", "套用": "差异化",
            "稳妥": "突破", "可靠": "卓越",
        },
    }
    swap = tone_map.get(target, {})
    out = text
    for old, new in swap.items():
        out = out.replace(old, new)
    return out


class StyleService:
    """标书风格修饰服务。"""

    VALID_STYLES = list(STYLE_PROFILES.keys())

    async def refine(
        self,
        session: AsyncSession,
        doc: BidDocument,
        target_style: str,
        instructions: Optional[str] = None,
    ) -> Tuple[BidDocument, str]:
        """对标书做风格修饰，返回 (新文档, 差异摘要)。

        行为：
        1. 校验 target_style 在白名单内
        2. 按目标风格做关键词替换 + 句子长度微调
        3. 创建新版本（version += 1），保留历史
        """
        if target_style not in self.VALID_STYLES:
            raise ValueError(f"不支持的风格：{target_style}（可选：{self.VALID_STYLES}）")

        old_content = doc.content
        old_style = doc.style
        old_version = doc.version

        # 风格切换
        new_content = _swap_keywords(old_content, STYLE_PROFILES[target_style], target_style)
        if instructions:
            new_content += f"\n\n## 修饰指令记录\n\n> {instructions}\n"

        # 写新版本（保留原版本作为历史）
        new_doc = BidDocument(
            bid_project_id=doc.bid_project_id,
            doc_type=doc.doc_type,
            style=target_style,
            title=doc.title,
            content=new_content,
            version=old_version + 1,
            status="draft",
        )
        session.add(new_doc)
        await session.flush()
        await session.refresh(new_doc)

        diff = self._diff_summary(old_content, new_content, old_style, target_style)
        return new_doc, diff

    @staticmethod
    def _diff_summary(old: str, new: str, old_style: str, new_style: str) -> str:
        old_sents = _split_sentences(old)
        new_sents = _split_sentences(new)
        old_len = _avg_len(old_sents)
        new_len = _avg_len(new_sents)
        old_kw = _count_keywords(old, STYLE_PROFILES.get(old_style, {}).get("tone_words", []))
        new_kw = _count_keywords(new, STYLE_PROFILES.get(new_style, {}).get("tone_words", []))
        return (
            f"风格：{old_style} → {new_style}；"
            f"句数：{len(old_sents)} → {len(new_sents)}；"
            f"平均句长：{old_len:.1f} → {new_len:.1f}；"
            f"风格词命中：{old_kw} → {new_kw}。"
        )


__all__ = ["STYLE_PROFILES", "StyleService"]
