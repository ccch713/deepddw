"""苏格拉底对话引擎（DDW AI Hub v5.4 — 培训插件 E1）。

工作原理：
- 加载 ``config/pedagogy/six_moves.yaml`` + ``socratic_lens.yaml`` + ``twelve_vignettes.yaml``
- 根据当前 ``move_id`` 选择 prompt
- 调用 LLM（通过 ``embedded_llm`` 或 stub）生成引导问题
- 评估学生回答（4 维度审计）
- 推进会话状态
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    session_id: str
    user_id: int
    tenant_id: int
    course_id: str
    subject: str
    concept: Optional[str] = None
    chapter: Optional[str] = None
    current_move: int = 1
    moves_completed: List[int] = field(default_factory=list)
    vignettes_used: List[int] = field(default_factory=list)
    turns: List[Dict[str, Any]] = field(default_factory=list)
    scores: Dict[str, float] = field(default_factory=lambda: {
        "conceptual_clarity": 0.0,
        "reasoning_depth": 0.0,
        "engagement_quality": 0.0,
        "pedagogical_alignment": 0.0,
    })
    status: str = "active"  # active / completed / abandoned
    started_at: float = 0.0


class SocraticEngine:
    """加载 pedagogy 配置 + 管理会话状态。LLM 调用通过注入的 ``llm_client`` 完成。"""

    def __init__(self, config_dir: Path, llm_client: Optional[Any] = None) -> None:
        self.config_dir = Path(config_dir)
        self._moves = self._load_yaml("pedagogy/six_moves.yaml").get("moves", [])
        self._lens = self._load_yaml("pedagogy/socratic_lens.yaml")
        self._vignettes = self._load_yaml("pedagogy/twelve_vignettes.yaml").get("vignettes", [])
        # craft-your-textbook 是 6 阶段造书流程，可选加载（缺文件时降级为 None）
        try:
            self._craft_textbook = self._load_yaml("pedagogy/craft_your_textbook.yaml")
        except FileNotFoundError:
            self._craft_textbook = None
        self.subjects: Dict[str, Any] = {}
        for f in (self.config_dir / "subjects").glob("*.yaml"):
            sub = self._load_yaml(f"subjects/{f.name}")
            self.subjects[sub["subject"]] = sub
        self.llm_client = llm_client
        craft_stages = len((self._craft_textbook or {}).get("stages", []))
        logger.info(
            "SocraticEngine loaded: %d moves, %d vignettes, %d subjects, craft_textbook stages=%d",
            len(self._moves), len(self._vignettes), len(self.subjects), craft_stages,
        )

    def _load_yaml(self, rel: str) -> Dict[str, Any]:
        with open(self.config_dir / rel, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    # ------------------------------------------------------------------ #
    # 对话推进
    # ------------------------------------------------------------------ #

    def start_session(self, session: SessionState) -> Dict[str, Any]:
        """启动会话：返回第一个 move 的引导问题。"""
        move = self._get_move(1)
        vignette = self._pick_vignette()
        session.vignettes_used.append(vignette["id"])
        opening = self._format_prompt(move, vignette, subject=session.subject, concept=session.concept)
        session.turns.append({"role": "assistant", "move": 1, "vignette": vignette["id"], "content": opening})
        return {"move": 1, "vignette": vignette["display"], "content": opening}

    async def next_turn(self, session: SessionState, student_message: str) -> Dict[str, Any]:
        """处理学生回答 → 评分 → 推进 move。"""
        session.turns.append({"role": "student", "content": student_message})
        # 评估（本地启发式 + 可选 LLM）
        eval_ = await self._evaluate(session, student_message)
        for k, v in eval_.items():
            session.scores[k] = (session.scores[k] + v) / 2 if session.scores[k] else v

        # 推进 move
        if session.current_move not in session.moves_completed:
            session.moves_completed.append(session.current_move)
        next_move_id = session.current_move + 1
        if next_move_id > len(self._moves):
            session.status = "completed"
            return {
                "move": session.current_move,
                "vignette": None,
                "content": "本节我们完成了所有 6 个思维动作。来看一下你的整体表现：\n\n" +
                           self._format_summary(session),
                "completed": True,
                "scores": session.scores,
            }
        session.current_move = next_move_id
        move = self._get_move(next_move_id)
        vignette = self._pick_vignette()
        session.vignettes_used.append(vignette["id"])
        reply = self._format_prompt(move, vignette, subject=session.subject, concept=session.concept, last_answer=student_message)
        session.turns.append({"role": "assistant", "move": next_move_id, "vignette": vignette["id"], "content": reply})
        return {"move": next_move_id, "vignette": vignette["display"], "content": reply, "scores": session.scores}

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #

    def _get_move(self, move_id: int) -> Dict[str, Any]:
        for m in self._moves:
            if m["id"] == move_id:
                return m
        return self._moves[0]

    def _pick_vignette(self) -> Dict[str, Any]:
        return random.choice(self._vignettes)

    def _format_prompt(self, move: Dict[str, Any], vignette: Dict[str, Any], **ctx) -> str:
        prompt = move["prompt"]
        sub = ctx.get("subject", "")
        concept = ctx.get("concept", "本节核心概念")
        if sub:
            return f"【{vignette['display']}】 {prompt}（{sub} - {concept}）"
        return f"【{vignette['display']}】 {prompt}"

    async def _evaluate(self, session: SessionState, message: str) -> Dict[str, float]:
        """本地启发式评分（生产可被 LLM 增强）。"""
        text = (message or "").strip()
        length = len(text)
        has_question = "?" in text or "？" in text
        has_example = any(k in text for k in ["比如", "例如", "像", "比方说", "如"])
        has_reason = any(k in text for k in ["因为", "所以", "因此", "由于", "导致"])
        return {
            "conceptual_clarity": min(1.0, 0.3 + length / 200),
            "reasoning_depth": 0.6 if has_reason else 0.3,
            "engagement_quality": 0.8 if has_question else (0.6 if has_example else 0.4),
            "pedagogical_alignment": 0.7 if length > 10 else 0.4,
        }

    def _format_summary(self, session: SessionState) -> str:
        s = session.scores
        overall = sum(s.values()) / max(1, len(s))
        grade = "A" if overall >= 0.85 else "B" if overall >= 0.7 else "C" if overall >= 0.55 else "D"
        return (
            f"- 概念清晰度：{s['conceptual_clarity']:.0%}\n"
            f"- 推理深度：{s['reasoning_depth']:.0%}\n"
            f"- 参与质量：{s['engagement_quality']:.0%}\n"
            f"- 教学对齐：{s['pedagogical_alignment']:.0%}\n"
            f"- 整体评级：{grade}"
        )


__all__ = ["SessionState", "SocraticEngine"]
