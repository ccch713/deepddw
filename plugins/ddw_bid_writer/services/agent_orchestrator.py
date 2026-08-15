"""E 方案：多 Agent 编排器。

通过 core/mcp 工具调度 LLM，实现：
- Planner：拆解任务、生成大纲
- Writer：单章生成（可并发）
- Reviewer：审查 + 一致性检查
- Editor：润色 + 统稿

每个 Agent 是一个 system prompt 角色，调用同一个 ddw.llm.chat MCP 工具。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from plugins.ddw_bid_writer.services.consistency_checker import ConsistencyChecker
from plugins.ddw_bid_writer.services.fact_sheet import fact_sheet_from_dict
from plugins.ddw_bid_writer.services.mcp_client import MCPClient, get_mcp_client
from plugins.ddw_bid_writer.services.outline_planner import OutlinePlanner
from plugins.ddw_bid_writer.services.polisher import Polisher
from plugins.ddw_bid_writer.services.section_writer import SectionWriter

logger = logging.getLogger(__name__)


class AgentRole(str, Enum):
    """多 Agent 角色。"""
    PLANNER = "planner"
    WRITER = "writer"
    REVIEWER = "reviewer"
    EDITOR = "editor"


@dataclass
class AgentStep:
    """单个 Agent 步骤的执行记录（用于审计 / 调试）。"""
    role: AgentRole
    started_at: float
    finished_at: float = 0.0
    input_summary: str = ""
    output_summary: str = ""
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role.value,
            "duration_ms": int((self.finished_at - self.started_at) * 1000),
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "success": self.success,
            "error": self.error,
            "metadata": self.metadata,
        }


class AgentOrchestrator:
    """多 Agent 编排器：把 4 个阶段串成 Agent 链路。"""

    def __init__(self) -> None:
        self.mcp: MCPClient = get_mcp_client()
        self.planner = OutlinePlanner()
        self.writer = SectionWriter()
        self.checker = ConsistencyChecker()
        self.polisher = Polisher()
        self.trace: List[AgentStep] = []

    # ----------------- 全流程编排 ----------------- #

    async def run(
        self,
        project: Dict[str, Any],
        doc_type: str = "技术标",
        style: str = "标准",
        tenant_id: int = 1,
        template_id: Optional[int] = None,
        template_sections: Optional[List[str]] = None,
        progress_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """执行完整 4 阶段流程。返回 {content, fact_sheet, sections, trace, conflicts}。"""
        self.trace = []
        # 阶段 1：Planner
        if progress_callback:
            try:
                progress_callback(stage="planner", progress=0.05, message="Agent Planner：生成大纲…")
            except Exception:  # noqa: BLE001
                pass
        planner_result = await self._run_agent(
            AgentRole.PLANNER,
            input_summary=f"project={project.get('project_name')}, doc_type={doc_type}",
            fn=lambda: self.planner.plan(project, doc_type, style, template_sections),
        )
        sections_plan = planner_result["sections"]
        fact_sheet = fact_sheet_from_dict(planner_result["fact_sheet"])

        # 阶段 2：Writer（多 Writer 并发，对应多章节）
        if progress_callback:
            try:
                progress_callback(stage="writer", progress=0.3, message="Agent Writer × N：并发生成章节…")
            except Exception:  # noqa: BLE001
                pass
        written_sections = await self.writer.write_all(
            project=project,
            doc_type=doc_type,
            style=style,
            sections=sections_plan,
            fact_sheet=fact_sheet,
            tenant_id=tenant_id,
            rag_top_k=3,
        )
        self._record(
            AgentRole.WRITER,
            input_summary=f"{len(sections_plan)} sections",
            output_summary=f"{sum(len(s.get('content', '')) for s in written_sections)} chars",
        )

        # 阶段 3：Reviewer
        if progress_callback:
            try:
                progress_callback(stage="reviewer", progress=0.6, message="Agent Reviewer：跨章一致性检查…")
            except Exception:  # noqa: BLE001
                pass
        check_result = await self._run_agent(
            AgentRole.REVIEWER,
            input_summary=f"{len(written_sections)} sections",
            fn=lambda: self.checker.check(fact_sheet, written_sections),
        )
        # 更新 fact_sheet（reviewer 抽到的新事实）
        fact_sheet = fact_sheet_from_dict(check_result["fact_sheet"])
        # 局部重写
        if check_result.get("conflicts"):
            written_sections = await self.checker.fix_conflicts(
                fact_sheet, written_sections, check_result["conflicts"]
            )

        # 阶段 4：Editor
        if progress_callback:
            try:
                progress_callback(stage="editor", progress=0.85, message="Agent Editor：全文润色…")
            except Exception:  # noqa: BLE001
                pass
        polished = await self._run_agent(
            AgentRole.EDITOR,
            input_summary=f"{len(written_sections)} sections, {check_result.get('conflict_count', 0)} conflicts",
            fn=lambda: self.polisher.polish(project, doc_type, style, written_sections, fact_sheet),
        )
        final_content = polished.get("content", "")
        if progress_callback:
            try:
                progress_callback(stage="done", progress=1.0, message="全部完成")
            except Exception:  # noqa: BLE001
                pass

        return {
            "content": final_content,
            "sections": written_sections,
            "fact_sheet": fact_sheet.to_dict(),
            "trace": [s.to_dict() for s in self.trace],
            "conflicts": check_result.get("conflicts", []),
            "polish_diff": polished.get("diff_summary", ""),
        }

    # ----------------- Agent 调用辅助 ----------------- #

    async def _run_agent(self, role: AgentRole, input_summary: str, fn) -> Any:
        """执行一个 agent 步骤，自动记录 trace。"""
        step = AgentStep(role=role, started_at=time.time(), input_summary=input_summary)
        try:
            result = await fn()
            step.finished_at = time.time()
            step.success = True
            step.output_summary = self._summarize_output(role, result)
            self.trace.append(step)
            return result
        except Exception as e:  # noqa: BLE001
            step.finished_at = time.time()
            step.success = False
            step.error = str(e)
            self.trace.append(step)
            logger.exception("agent %s failed", role.value)
            raise

    @staticmethod
    def _summarize_output(role: AgentRole, result: Any) -> str:
        if role == AgentRole.PLANNER:
            return f"{len(result.get('sections', []))} sections, {result.get('total_target_words', 0)} target words"
        if role == AgentRole.WRITER:
            return f"{len(result)} sections written"
        if role == AgentRole.REVIEWER:
            return f"{result.get('conflict_count', 0)} conflicts"
        if role == AgentRole.EDITOR:
            return result.get("diff_summary", "")
        return ""

    def _record(self, role: AgentRole, input_summary: str, output_summary: str) -> None:
        """记录一个外部 agent 步骤（用于 writer 多并发场景）。"""
        now = time.time()
        self.trace.append(AgentStep(
            role=role,
            started_at=now,
            finished_at=now,
            input_summary=input_summary,
            output_summary=output_summary,
            success=True,
        ))


__all__ = ["AgentOrchestrator", "AgentRole", "AgentStep"]
