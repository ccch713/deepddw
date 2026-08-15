"""AI 出题 + 自动评分（DDW AI Hub v5.4 — 培训插件 E1）。"""

from __future__ import annotations

import logging
import random
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# 题目模板（生产应从 LLM 动态生成）
_QUESTION_TEMPLATES = {
    "physics": [
        {"id": "phy-1", "concept": "速度", "q": "小明 5 秒跑了 25 米，他的平均速度是多少？单位 m/s。", "answer": "5", "tolerance": 0.1, "type": "numeric"},
        {"id": "phy-2", "concept": "加速度", "q": "汽车从 0 加速到 20 m/s 用了 4 秒，加速度是多少 m/s²？", "answer": "5", "tolerance": 0.1, "type": "numeric"},
        {"id": "phy-3", "concept": "牛顿第一定律", "q": "在光滑水平面上运动的物体会停下来吗？为什么？", "answer_keywords": ["不会", "惯性", "无摩擦"], "type": "short_answer"},
    ],
    "chemistry": [
        {"id": "che-1", "concept": "空气的成分", "q": "空气中含量最多的气体是什么？体积分数约 78%。", "answer": "氮气", "type": "text"},
        {"id": "che-2", "concept": "氧气", "q": "氧气（O₂）的化学式读作？", "answer": "氧气", "type": "text"},
        {"id": "che-3", "concept": "分子", "q": "分子是保持物质化学性质的最小粒子吗？", "answer": "是", "type": "text"},
    ],
}


class AssessmentEngine:
    def __init__(self) -> None:
        self._templates = _QUESTION_TEMPLATES
        logger.info("AssessmentEngine loaded for subjects: %s", list(self._templates.keys()))

    def generate_quiz(self, subject: str, n: int = 5) -> List[Dict[str, Any]]:
        pool = list(self._templates.get(subject, []))
        if not pool:
            return []
        n = min(n, len(pool))
        return random.sample(pool, n)

    def grade(self, question: Dict[str, Any], student_answer: str) -> Dict[str, Any]:
        """自动评分。返回 {score: 0-1, correct: bool, feedback: str}。"""
        if question.get("type") == "numeric":
            try:
                v = float(student_answer.strip())
                target = float(question["answer"])
                tol = float(question.get("tolerance", 0))
                ok = abs(v - target) <= tol
                return {"score": 1.0 if ok else 0.0, "correct": ok, "feedback": f"标准答案 {target}（容差 {tol}）"}
            except (ValueError, TypeError):
                return {"score": 0.0, "correct": False, "feedback": "请输入数字"}
        if question.get("type") == "text":
            ans = (student_answer or "").strip()
            target = (question.get("answer") or "").strip()
            ok = ans == target or target in ans
            return {"score": 1.0 if ok else 0.0, "correct": ok, "feedback": f"标准答案：{target}"}
        if question.get("type") == "short_answer":
            kws = question.get("answer_keywords") or []
            ans = (student_answer or "").lower()
            hit = sum(1 for k in kws if k.lower() in ans)
            ratio = hit / max(1, len(kws))
            return {"score": ratio, "correct": ratio >= 0.5, "feedback": f"命中关键词 {hit}/{len(kws)}"}
        return {"score": 0.0, "correct": False, "feedback": "未知题型"}

    def overall_grade(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """根据多次评分计算 4 维度 + 总分 + grade（A/B/C/D）。"""
        if not results:
            return {"score": 0.0, "grade": "D", "by_dimension": {}}
        total = sum(r.get("score", 0) for r in results) / len(results)
        # 简化映射
        by_dim = {
            "conceptual_clarity": min(1.0, 0.4 + total * 0.6),
            "reasoning_depth": min(1.0, 0.3 + total * 0.7),
            "engagement_quality": min(1.0, 0.5 + total * 0.5),
            "pedagogical_alignment": min(1.0, 0.4 + total * 0.6),
        }
        grade = "A" if total >= 0.85 else "B" if total >= 0.7 else "C" if total >= 0.55 else "D"
        return {"score": total, "grade": grade, "by_dimension": by_dim}


__all__ = ["AssessmentEngine"]
