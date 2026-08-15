"""标书审查：合规检查 + 评分 + 建议。"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_bid_writer.models import BidDocument

logger = logging.getLogger(__name__)


DEFAULT_CHECK_ITEMS = [
    "章节完整性",
    "关键字段（项目名/客户/金额/截止）",
    "敏感词",
    "字符长度",
    "结构层级",
    "联系人/电话",
]


# 审查词库（从独立配置加载，避免敏感词出现在源码注释中）
def _load_prohibited_terms() -> list[str]:
    """从外部 config 加载审查词库；找不到时使用内置兜底。"""
    from pathlib import Path
    cfg = Path(__file__).resolve().parent.parent / "config" / "prohibited_terms.json"
    if cfg.exists():
        import json
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            # 兼容两种结构：纯 list 或 {terms: [...]}
            if isinstance(data, list):
                return [str(x) for x in data]
            if isinstance(data, dict):
                return [str(x) for x in data.get("terms", [])]
        except Exception:  # noqa: BLE001
            pass
    # 兜底（仅在本地开发用；生产必须通过 config 注入）
    return []


PROHIBITED_TERMS = _load_prohibited_terms()


class ReviewService:
    """标书审查服务。"""

    async def review(
        self,
        session: AsyncSession,
        doc: BidDocument,
        check_items: List[str] | None = None,
    ) -> Dict[str, Any]:
        items = check_items or DEFAULT_CHECK_ITEMS
        issues: List[Dict[str, Any]] = []

        for item in items:
            method = getattr(self, f"_check_{_to_snake(item)}", None)
            if method is None:
                issues.append({
                    "severity": "warn",
                    "category": item,
                    "message": f"无内置检查项：{item}",
                })
                continue
            item_issues = method(doc)
            issues.extend(item_issues)

        # 评分：100 - 各 severity 扣分
        score = 100.0
        for iss in issues:
            sev = iss.get("severity", "info")
            if sev == "error":
                score -= 15
            elif sev == "warn":
                score -= 5
            else:
                score -= 1
        score = max(0.0, min(100.0, score))

        # 写回 doc
        doc.review_score = round(score, 1)
        doc.review_notes = "; ".join(f"[{i['severity']}] {i['category']}: {i['message']}" for i in issues[:10])
        doc.status = "reviewed"
        await session.flush()

        # 建议
        suggestions = self._suggest(issues, score)

        return {
            "document_id": doc.id,
            "score": round(score, 1),
            "issues": issues,
            "summary": self._summarize(score, issues),
            "suggestions": suggestions,
        }

    # ----------------- 检查项实现 ----------------- #

    @staticmethod
    def _check_section_completeness(doc: BidDocument) -> List[Dict[str, Any]]:
        """章节完整性：检查 Markdown 二级标题数量。"""
        headings = re.findall(r"^##\s+", doc.content, re.MULTILINE)
        out = []
        if len(headings) < 3:
            out.append({
                "severity": "error",
                "category": "章节完整性",
                "message": f"仅有 {len(headings)} 个二级标题，建议至少 3 个章节",
            })
        else:
            out.append({
                "severity": "info",
                "category": "章节完整性",
                "message": f"已包含 {len(headings)} 个二级标题",
            })
        return out

    @staticmethod
    def _check_key_fields(doc: BidDocument) -> List[Dict[str, Any]]:
        """关键字段：在标书头部应包含项目基本信息。"""
        out = []
        # 取头部 800 字
        head = doc.content[:800]
        if "项目类型" not in head and "project_type" not in head.lower():
            out.append({"severity": "warn", "category": "关键字段", "message": "未在标书头部明确项目类型"})
        if "估算金额" not in head and "estimated_amount" not in head.lower():
            out.append({"severity": "warn", "category": "关键字段", "message": "未在标书头部明确估算金额"})
        if not out:
            out.append({"severity": "info", "category": "关键字段", "message": "关键字段已就位"})
        return out

    @staticmethod
    def _check_sensitive_words(doc: BidDocument) -> List[Dict[str, Any]]:
        """敏感词扫描。"""
        out = []
        hits = [w for w in PROHIBITED_TERMS if w in doc.content]
        if hits:
            out.append({
                "severity": "error",
                "category": "敏感词",
                "message": f"检测到敏感词：{', '.join(hits)}，请立即删除",
            })
        else:
            out.append({"severity": "info", "category": "敏感词", "message": "未检测到敏感词"})
        return out

    @staticmethod
    def _check_length(doc: BidDocument) -> List[Dict[str, Any]]:
        """字符长度：标书正文建议 1500-50000 字符。"""
        out = []
        n = len(doc.content or "")
        if n < 1500:
            out.append({"severity": "warn", "category": "字符长度", "message": f"标书过短（{n} 字符），建议补充内容"})
        elif n > 50000:
            out.append({"severity": "warn", "category": "字符长度", "message": f"标书过长（{n} 字符），建议精简"})
        else:
            out.append({"severity": "info", "category": "字符长度", "message": f"长度适中（{n} 字符）"})
        return out

    @staticmethod
    def _check_structure(doc: BidDocument) -> List[Dict[str, Any]]:
        """结构层级：是否使用了 Markdown 标题层级。"""
        h1 = re.findall(r"^#\s+", doc.content, re.MULTILINE)
        h2 = re.findall(r"^##\s+", doc.content, re.MULTILINE)
        out = []
        if not h1:
            out.append({"severity": "warn", "category": "结构层级", "message": "缺少一级标题"})
        if not h2:
            out.append({"severity": "warn", "category": "结构层级", "message": "缺少二级标题"})
        if h1 and h2 and not out:
            out.append({"severity": "info", "category": "结构层级", "message": f"层级正常（H1×{len(h1)}，H2×{len(h2)}）"})
        return out

    @staticmethod
    def _check_contact(doc: BidDocument) -> List[Dict[str, Any]]:
        """联系人/电话：是否含联系方式。"""
        out = []
        has_phone = bool(re.search(r"1[3-9]\d{9}", doc.content))
        has_email = bool(re.search(r"[\w.-]+@[\w.-]+\.\w+", doc.content))
        if not has_phone and not has_email:
            out.append({"severity": "warn", "category": "联系人/电话", "message": "未提供联系电话或邮箱"})
        else:
            out.append({"severity": "info", "category": "联系人/电话", "message": "联系方式已就位"})
        return out

    # ----------------- 工具 ----------------- #

    @staticmethod
    def _summarize(score: float, issues: List[Dict[str, Any]]) -> str:
        n_err = sum(1 for i in issues if i.get("severity") == "error")
        n_warn = sum(1 for i in issues if i.get("severity") == "warn")
        level = "优秀" if score >= 90 else "良好" if score >= 75 else "合格" if score >= 60 else "不合格"
        return f"评分 {score}（{level}），error ×{n_err}，warn ×{n_warn}。"

    @staticmethod
    def _suggest(issues: List[Dict[str, Any]], score: float) -> List[str]:
        out: List[str] = []
        if any(i["category"] == "敏感词" and i["severity"] == "error" for i in issues):
            out.append("【紧急】立即删除全部敏感词，避免合规风险")
        if any(i["category"] == "章节完整性" and i["severity"] == "error" for i in issues):
            out.append("补充至少 3 个二级章节，覆盖技术/商务/资质等关键维度")
        if any(i["category"] == "关键字段" and i["severity"] == "warn" for i in issues):
            out.append("在标书头部明确项目类型、估算金额、截止时间")
        if any(i["category"] == "字符长度" and i["severity"] == "warn" for i in issues):
            out.append("调整标书长度至 1500-50000 字符")
        if any(i["category"] == "联系人/电话" and i["severity"] == "warn" for i in issues):
            out.append("添加 11 位手机号或企业邮箱，方便业主联系")
        if score < 75:
            out.append("整体评分偏低，建议走一轮标书风格修饰（refine）后再提交")
        return out


def _to_snake(s: str) -> str:
    """中文检查项转拼音/英文函数名（这里做简化映射）。"""
    mapping = {
        "章节完整性": "section_completeness",
        "关键字段（项目名/客户/金额/截止）": "key_fields",
        "敏感词": "sensitive_words",
        "字符长度": "length",
        "结构层级": "structure",
        "联系人/电话": "contact",
    }
    return mapping.get(s, "unknown")


__all__ = ["DEFAULT_CHECK_ITEMS", "ReviewService"]
