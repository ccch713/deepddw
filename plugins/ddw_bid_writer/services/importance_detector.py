"""F 方案：重要项目检测 + 渐进式披露推荐。

判断逻辑（基于规则 + 可选 LLM）：
- 金额 >= 阈值（默认 1 亿）
- 截止时间 <= 7 天
- 客户首次投标
- 用户手动标记
→ 提示「建议渐进式披露」
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ImportanceLevel(str, Enum):
    """项目重要级别。"""
    ROUTINE = "routine"  # 普通：自动模式
    IMPORTANT = "important"  # 重要：推荐渐进式
    CRITICAL = "critical"  # 关键：强烈推荐渐进式


@dataclass
class ImportanceAssessment:
    """重要级别评估结果。"""
    level: ImportanceLevel
    score: float  # 0-1
    reasons: list  # 触发原因
    recommended_mode: str  # auto / important
    message: str  # 给用户的提示

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level.value,
            "score": round(self.score, 3),
            "reasons": self.reasons,
            "recommended_mode": self.recommended_mode,
            "message": self.message,
        }


class ImportanceDetector:
    """重要项目检测器。"""

    def __init__(
        self,
        amount_threshold: float = 1e8,  # 1 亿
        critical_amount: float = 5e8,  # 5 亿
        urgent_days: int = 7,  # 7 天内
    ) -> None:
        self.amount_threshold = amount_threshold
        self.critical_amount = critical_amount
        self.urgent_days = urgent_days

    def assess(
        self,
        project: Dict[str, Any],
        is_first_with_client: bool = False,
        user_marked: Optional[str] = None,
    ) -> ImportanceAssessment:
        """评估项目重要级别。"""
        reasons: list = []
        score = 0.0

        # 1. 用户手动标记（最高优先级）
        if user_marked == "critical":
            return ImportanceAssessment(
                level=ImportanceLevel.CRITICAL,
                score=1.0,
                reasons=["用户手动标记为关键"],
                recommended_mode="important",
                message="该项目已被您标记为关键，强烈建议走渐进式披露。",
            )
        if user_marked == "important":
            return ImportanceAssessment(
                level=ImportanceLevel.IMPORTANT,
                score=0.8,
                reasons=["用户手动标记为重要"],
                recommended_mode="important",
                message="该项目已被您标记为重要，建议走渐进式披露。",
            )
        if user_marked == "routine":
            return ImportanceAssessment(
                level=ImportanceLevel.ROUTINE,
                score=0.2,
                reasons=["用户手动标记为普通"],
                recommended_mode="auto",
                message="已按普通项目处理。",
            )

        # 2. 金额评估
        amount = float(project.get("estimated_amount") or 0)
        if amount >= self.critical_amount:
            reasons.append(f"金额 {amount/1e8:.1f} 亿元，超过 5 亿关键线")
            score += 0.5
        elif amount >= self.amount_threshold:
            reasons.append(f"金额 {amount/1e8:.2f} 亿元，超过 1 亿重要线")
            score += 0.3

        # 3. 截止时间评估
        deadline = project.get("bid_deadline")
        if deadline:
            try:
                if isinstance(deadline, str):
                    dt = datetime.fromisoformat(deadline.replace("Z", "+00:00").replace("T", " ").split("+")[0].strip())
                else:
                    dt = deadline
                days_left = (dt - datetime.now()).days
                if days_left <= 3:
                    reasons.append(f"截止时间紧迫（剩 {days_left} 天）")
                    score += 0.3
                elif days_left <= self.urgent_days:
                    reasons.append(f"截止时间较紧（剩 {days_left} 天）")
                    score += 0.2
            except (ValueError, TypeError):
                pass

        # 4. 客户首次
        if is_first_with_client:
            reasons.append("该客户首次合作，无历史标书参考")
            score += 0.15

        # 5. 项目类型（重要类型）
        important_types = {"市政", "工业", "医院", "学校", "政府"}
        pt = project.get("project_type", "")
        if any(t in pt for t in important_types):
            reasons.append(f"项目类型 {pt} 属重要类别")
            score += 0.1

        # 6. 判定
        if score >= 0.6:
            level = ImportanceLevel.CRITICAL
            recommended = "important"
            msg = "⚠️ 关键项目：建议走渐进式披露，逐章确认后再合并提交。"
        elif score >= 0.3:
            level = ImportanceLevel.IMPORTANT
            recommended = "important"
            msg = "💡 重要项目：建议走渐进式披露，逐章审阅后再提交。"
        else:
            level = ImportanceLevel.ROUTINE
            recommended = "auto"
            msg = "✓ 普通项目：可使用自动模式，全流程一键完成。"

        return ImportanceAssessment(
            level=level,
            score=min(1.0, score),
            reasons=reasons,
            recommended_mode=recommended,
            message=msg,
        )


__all__ = ["ImportanceAssessment", "ImportanceDetector", "ImportanceLevel"]
