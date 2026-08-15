"""标书生成服务（v2.0 — C+D+E+F 编排器）。

向后兼容：保留旧的 ``generate()`` 接口，内部委托 ``AgentOrchestrator``。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_bid_writer.models import (
    AgentRun,
    BidDocument,
    BidProject,
    BidSection,
)
from plugins.ddw_bid_writer.services.agent_orchestrator import AgentOrchestrator
from plugins.ddw_bid_writer.services.outline_planner import DEFAULT_SECTIONS

logger = logging.getLogger(__name__)


# Re-export for backward compat
__all__ = ["DEFAULT_SECTIONS", "GenerateService"]


def _project_to_dict(p: BidProject) -> Dict[str, Any]:
    return {
        "id": p.id,
        "project_name": p.project_name,
        "client_name": p.client_name,
        "project_type": p.project_type,
        "estimated_amount": p.estimated_amount,
        "bid_deadline": p.bid_deadline.isoformat() if p.bid_deadline else None,
        "structure_type": "",  # BidProject 模型没有这个字段；调用方可注入
        "floor_count": 0,
        "area_sqm": 0.0,
        "status": p.status,
    }


def _build_skeleton(project: BidProject, doc_type: str, template: Optional[Any]) -> str:
    """兼容旧版接口的骨架生成（用于 mode=legacy 或 template-only 场景）。"""
    sections = DEFAULT_SECTIONS.get(doc_type, DEFAULT_SECTIONS["技术标"])
    header = [
        f"# {project.project_name} — {doc_type}",
        "",
        f"> 投标方：{project.client_name or '—'}",
        f"> 项目类型：{project.project_type or '—'}",
        f"> 估算金额：{project.estimated_amount or '—'} 元",
        f"> 投标截止：{project.bid_deadline.strftime('%Y-%m-%d %H:%M') if project.bid_deadline else '—'}",
        "",
        "---",
        "",
    ]
    body: List[str] = []
    for i, sec in enumerate(sections, 1):
        body.append(f"## {i}. {sec[0]}")
        body.append("")
        body.append(f"（待补充：{sec[1]}）")
        body.append("")
        body.append("")
    footer = [
        "---",
        "",
        f"_本标书由 DDW AI Hub 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_",
    ]
    text = "\n".join(header + body + footer)
    if template and getattr(template, "content", None):
        text = f"## 模板参考：{template.name}\n\n{template.content}\n\n---\n\n{text}"
    return text


class GenerateService:
    """标书生成服务（v2）。

    Modes:
    - "auto"     : C+D+E 全流程自动（默认；适合普通项目）
    - "important": F 渐进式披露模式（仅生成大纲 + 单章 API，由前端驱动）
    - "skeleton" : 仅阶段 1 大纲（最快）
    - "legacy"   : 旧版一次性生成（向后兼容，不走 LLM）
    """

    def __init__(self, use_llm: bool = False) -> None:
        self.use_llm = use_llm
        self.orchestrator = AgentOrchestrator()

    # ----------------- 新版：阶段 1 大纲 ----------------- #

    async def plan(
        self,
        session: AsyncSession,
        project: BidProject,
        doc_type: str = "技术标",
        style: str = "标准",
        template_sections: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """阶段 1：仅生成大纲，不生成正文。返回 sections + 初始 FactSheet。"""
        proj_dict = _project_to_dict(project)
        result = await self.orchestrator.planner.plan(proj_dict, doc_type, style, template_sections)
        return result

    # ----------------- 新版：完整 4 阶段 ----------------- #

    async def generate(
        self,
        session: AsyncSession,
        project: BidProject,
        doc_type: str = "技术标",
        style: str = "标准",
        title: Optional[str] = None,
        extra_requirements: Optional[str] = None,
        template_id: Optional[int] = None,
        mode: str = "auto",
    ) -> BidDocument:
        """新版生成（4 阶段流水线）。

        行为根据 mode：
        - "auto": C+D+E 全流程跑完，生成完整标书文档
        - "skeleton": 仅生成大纲 + FactSheet，正文用占位模板
        - "important": 同 auto，但额外记录 AgentRun 供渐进式披露
        - "legacy": 旧版一次性生成
        """
        proj_dict = _project_to_dict(project)

        # 模板
        template_sections: Optional[List[str]] = None
        if template_id:
            from plugins.ddw_bid_writer.models import BidTemplate

            tpl = (
                await session.execute(
                    select(BidTemplate).where(BidTemplate.id == template_id)
                )
            ).scalar_one_or_none()
            if tpl and tpl.content:
                # 简单处理：取模板的所有 ## 标题作为 sections
                import re
                template_sections = re.findall(r"^#{1,2}\s+(.+)$", tpl.content, re.MULTILINE)

        # AgentRun 记录
        agent_run = AgentRun(
            tenant_id=project.tenant_id,
            bid_project_id=project.id,
            mode=mode,
            status="running",
        )
        if mode in ("auto", "important"):
            session.add(agent_run)
            await session.flush()
            await session.refresh(agent_run)

        try:
            if mode == "legacy":
                # 旧版
                from plugins.ddw_bid_writer.models import BidTemplate
                tpl = (
                    await session.execute(
                        select(BidTemplate).where(BidTemplate.id == template_id)
                    )
                ).scalar_one_or_none() if template_id else None
                content = _build_skeleton(project, doc_type, tpl)
                if extra_requirements:
                    content += f"\n\n## 补充要求\n\n{extra_requirements}\n"
                project.status = "generating"
                doc = BidDocument(
                    bid_project_id=project.id,
                    doc_type=doc_type,
                    style=style,
                    title=title or f"{project.project_name}-{doc_type}",
                    content=content,
                    version=1,
                    status="draft",
                )
                session.add(doc)
                await session.flush()
                await session.refresh(doc)
                return doc

            # 新版：C+D+E 全流程
            result = await self.orchestrator.run(
                project=proj_dict,
                doc_type=doc_type,
                style=style,
                tenant_id=project.tenant_id,
                template_id=template_id,
                template_sections=template_sections,
            )
            content = result["content"]
            if extra_requirements:
                content += f"\n\n## 补充要求\n\n{extra_requirements}\n"

            project.status = "generating"
            doc = BidDocument(
                bid_project_id=project.id,
                doc_type=doc_type,
                style=style,
                title=title or f"{project.project_name}-{doc_type}",
                content=content,
                version=1,
                status="draft",
            )
            session.add(doc)
            await session.flush()
            await session.refresh(doc)

            # 写章节记录（让前端能逐章展示/锁定）
            for sec in result.get("sections", []):
                bs = BidSection(
                    bid_document_id=doc.id,
                    section_index=sec["index"],
                    section_title=sec["title"],
                    section_role="writer",
                    outline_summary=sec.get("summary", ""),
                    content=sec.get("content", ""),
                    rag_context=sec.get("rag_context", ""),
                    fact_sheet_snapshot=json.dumps(result.get("fact_sheet", {}), ensure_ascii=False),
                )
                session.add(bs)
            await session.flush()

            # 更新 AgentRun
            if agent_run.id:
                agent_run.bid_document_id = doc.id
                agent_run.agents_trace = json.dumps(result.get("trace", []), ensure_ascii=False, default=str)
                agent_run.status = "success"
                from datetime import datetime as _dt
                agent_run.finished_at = _dt.utcnow()
                await session.flush()

            return doc

        except Exception as e:  # noqa: BLE001
            if agent_run.id:
                agent_run.status = "failed"
                agent_run.error_msg = str(e)
                from datetime import datetime as _dt
                agent_run.finished_at = _dt.utcnow()
                await session.flush()
            raise
