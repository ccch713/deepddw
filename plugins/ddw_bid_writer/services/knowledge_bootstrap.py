"""历史标书学习（Knowledge Bootstrap）。

流程：文件夹 → 解析 → 分块 → embedding → 向量库 → 抽 FactTemplate。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_bid_writer.models import (
    FactTemplate,
    KnowledgeBootstrapRun,
    KnowledgeDocument,
)
from plugins.ddw_bid_writer.services.fact_sheet import (
    extract_metrics,
    extract_personnel,
)
from plugins.ddw_bid_writer.services.vector_store import TenantKnowledgeStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 文件解析（零外部依赖版）
# ---------------------------------------------------------------------------


# 支持的扩展名 + 对应解析器
SUPPORTED_EXTS = {".md", ".markdown", ".txt", ".json", ".yaml", ".yml"}
# 暂支持的提示：实际部署时安装 pypdf / python-docx 后可扩展
CONDITIONAL_EXTS = {".pdf", ".docx", ".doc"}


def parse_file(path: Path) -> Tuple[str, Optional[str]]:
    """解析文件为纯文本。返回 (text, error_or_None)。"""
    if not path.exists():
        return "", f"file not found: {path}"
    ext = path.suffix.lower()
    if ext in {".md", ".markdown", ".txt"}:
        try:
            return path.read_text(encoding="utf-8"), None
        except UnicodeDecodeError:
            try:
                return path.read_text(encoding="gbk"), None
            except Exception as e:  # noqa: BLE001
                return "", f"decode failed: {e}"
    if ext == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return json.dumps(data, ensure_ascii=False, indent=2), None
        except Exception as e:  # noqa: BLE001
            return "", f"json parse failed: {e}"
    if ext in {".yaml", ".yml"}:
        try:
            import yaml

            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            return yaml.safe_dump(data, allow_unicode=True, sort_keys=False), None
        except Exception as e:  # noqa: BLE001
            return "", f"yaml parse failed: {e}"
    if ext in CONDITIONAL_EXTS:
        return "", (
            f"暂不支持 {ext} 格式。请安装 pypdf/python-docx 后重启，"
            f"或先将文件转换为 .md/.txt 格式"
        )
    return "", f"unsupported extension: {ext}"


# ---------------------------------------------------------------------------
# 文档分块
# ---------------------------------------------------------------------------


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_PARA_SPLIT = re.compile(r"\n\s*\n")


def chunk_text(text: str, target_size: int = 800, max_size: int = 1500) -> List[str]:
    """智能分块：按二级标题优先，单块控制在 target_size 字以内。

    算法：
    1. 先按二级标题（##）切大段
    2. 大段过长时再按段落切
    3. 单段过长时按 max_size 硬切
    """
    if not text or not text.strip():
        return []
    # 1. 按二级标题切
    sections: List[Tuple[str, str]] = []  # (heading, body)
    current_h = ""
    current_body: List[str] = []
    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m and len(m.group(1)) <= 2:  # # 或 ##
            if current_body or current_h:
                sections.append((current_h, "\n".join(current_body).strip()))
            current_h = m.group(2).strip()
            current_body = []
        else:
            current_body.append(line)
    if current_body or current_h:
        sections.append((current_h, "\n".join(current_body).strip()))

    # 2. 每段内部：按段落切，再合并到 target_size
    chunks: List[str] = []
    for heading, body in sections:
        if not body and not heading:
            continue
        full = f"## {heading}\n{body}".strip() if heading else body
        if len(full) <= max_size:
            chunks.append(full)
            continue
        # 段落级切
        paras = [p.strip() for p in _PARA_SPLIT.split(body) if p.strip()]
        buf: List[str] = []
        cur_len = len(heading) + 4  # ## xxx\n
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

    # 3. 过滤空块
    return [c for c in chunks if c.strip() and len(c.strip()) >= 20]


# ---------------------------------------------------------------------------
# FactTemplate 抽取
# ---------------------------------------------------------------------------


def extract_section_structure(text: str) -> List[str]:
    """抽取文档的章节结构（按一级/二级标题）。"""
    seen = set()
    out: List[str] = []
    for m in _HEADING_RE.finditer(text):
        if len(m.group(1)) <= 2:  # # 或 ##
            title = m.group(2).strip()
            if title and title not in seen:
                seen.add(title)
                out.append(title)
    return out


def extract_personnel_template(text: str) -> Dict[str, List[str]]:
    """抽取人员模板：角色 → 出现过的姓名列表。"""
    template: Dict[str, set] = {}
    for p in extract_personnel(text):
        template.setdefault(p.role, set()).add(p.name)
    return {role: sorted(list(names)) for role, names in template.items()}


def extract_metric_templates(text: str) -> Dict[str, List[float]]:
    """抽取指标模板：key → 所有出现过的数值。"""
    template: Dict[str, List[float]] = {}
    for m in extract_metrics(text):
        template.setdefault(m.key, []).append(m.value)
    return template


def detect_style_baseline(text: str) -> str:
    """从文档里推断风格基线（用高频风格词）。"""
    keywords = {
        "保守": ["稳妥", "可靠", "成熟", "沿用", "经验"],
        "激进": ["突破", "创新", "领先", "超越", "差异化"],
        "创新型": ["首创", "独家", "突破性", "革命性"],
        "标准": ["合理", "规范", "符合", "满足", "确保"],
    }
    scores = {k: sum(text.count(w) for w in words) for k, words in keywords.items()}
    dominant = max(scores, key=scores.get)
    if scores[dominant] == 0:
        return "本标书采用标准、稳健的表达风格。"
    style_map = {
        "保守": "本标书采用稳妥、可靠的表达，强调成熟工艺和既有经验。",
        "激进": "本标书采用突破、创新的表达，强调差异化优势和行业领先地位。",
        "创新型": "本标书采用首创、突破性的表达，强调独家方案和革命性技术。",
        "标准": "本标书采用标准、规范的表达，强调技术合理性和合规符合。",
    }
    return style_map[dominant]


# ---------------------------------------------------------------------------
# 知识库 Bootstrap 入口
# ---------------------------------------------------------------------------


class KnowledgeBootstrap:
    """历史标书学习流程。"""

    SUPPORTED_EXTS = SUPPORTED_EXTS

    def __init__(self, base_dir: str = "./data/bid_kb") -> None:
        self.base_dir = base_dir

    def _kb_for(self, tenant_id: int) -> TenantKnowledgeStore:
        return TenantKnowledgeStore(tenant_id, base_dir=self.base_dir)

    def _iter_files(self, folder: str) -> List[Path]:
        """列出文件夹中所有可解析的文件。"""
        p = Path(folder)
        if not p.exists() or not p.is_dir():
            return []
        out: List[Path] = []
        for f in p.rglob("*"):
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS:
                out.append(f)
        return sorted(out)

    async def run(
        self,
        session: AsyncSession,
        tenant_id: int,
        folder: str,
    ) -> Dict[str, Any]:
        """同步执行学习流程（不是真异步，但保留 async 接口方便后续并发）。"""
        # 1. 创建 run 记录
        run = KnowledgeBootstrapRun(tenant_id=tenant_id, folder=folder, status="running")
        session.add(run)
        await session.flush()
        await session.refresh(run)
        run_id = run.id

        files = self._iter_files(folder)
        run.total_files = len(files)
        await session.flush()

        kb = self._kb_for(tenant_id)
        success = 0
        failed = 0
        total_chunks = 0
        all_sections: Dict[str, List[str]] = {}
        all_personnel: Dict[str, set] = {}
        all_metrics: Dict[str, List[float]] = {}
        all_styles: List[str] = []

        for f in files:
            text, err = parse_file(f)
            if err or not text.strip():
                # 记录失败
                kd = KnowledgeDocument(
                    tenant_id=tenant_id,
                    doc_id=f"kb_{run_id}_{f.name}_{hash(str(f)) & 0xffffff:x}",
                    file_name=f.name,
                    file_path=str(f),
                    status="failed",
                    error_msg=err or "empty content",
                )
                session.add(kd)
                failed += 1
                continue

            # 推断 doc_type
            doc_type = None
            if "技术标" in f.name or "技术方案" in f.name:
                doc_type = "技术标"
            elif "商务标" in f.name or "报价" in f.name:
                doc_type = "商务标"
            elif "资格预审" in f.name:
                doc_type = "资格预审"
            project_type = None
            for pt in ("住宅", "商业", "工业", "市政"):
                if pt in text[:500] or pt in f.name:
                    project_type = pt
                    break

            # 分块
            chunks = chunk_text(text)
            if not chunks:
                failed += 1
                continue

            # 入向量库
            doc_id = f"kb_{run_id}_{f.stem}_{hash(str(f)) & 0xffffff:x}"
            metas = [
                {"doc_type": doc_type or "", "project_type": project_type or "", "file_name": f.name}
                for _ in chunks
            ]
            try:
                await kb.add_document_async(doc_id, chunks, metas)
            except Exception as e:  # noqa: BLE001
                logger.exception("add_document failed for %s", f)
                failed += 1
                continue

            # 累积模板
            sections = extract_section_structure(text)
            if sections:
                key = doc_type or "通用"
                all_sections.setdefault(key, []).extend(sections)
            pt = extract_personnel_template(text)
            for role, names in pt.items():
                all_personnel.setdefault(role, set()).update(names)
            mt = extract_metric_templates(text)
            for k, vs in mt.items():
                all_metrics.setdefault(k, []).extend(vs)
            style = detect_style_baseline(text)
            if style:
                all_styles.append(style)

            # 记录到 DB
            kd = KnowledgeDocument(
                tenant_id=tenant_id,
                doc_id=doc_id,
                file_name=f.name,
                file_path=str(f),
                doc_type=doc_type,
                project_type=project_type,
                raw_text=text[:50000],  # 截断
                chunk_count=len(chunks),
                status="ready",
            )
            session.add(kd)
            success += 1
            total_chunks += len(chunks)

        # 2. 抽取 FactTemplates（按 doc_type + project_type 聚合）
        templates_extracted = 0
        # 通用模板（不区分 doc_type）
        if all_sections or all_personnel or all_metrics or all_styles:
            tpl = FactTemplate(
                tenant_id=tenant_id,
                name=f"通用模板（{success} 个历史标书）",
                project_type=None,
                doc_type=None,
                section_structure=json.dumps(
                    {k: list(dict.fromkeys(v))[:20] for k, v in all_sections.items()}, ensure_ascii=False
                ),
                personnel_template=json.dumps(
                    {k: sorted(v) for k, v in all_personnel.items()}, ensure_ascii=False
                ),
                style_baseline=(
                    max(set(all_styles), key=all_styles.count) if all_styles else ""
                ),
                sample_count=success,
                is_default=not any(t.is_default for t in (
                    await session.execute(
                        select(FactTemplate).where(
                            FactTemplate.tenant_id == tenant_id, FactTemplate.is_default.is_(True)
                        )
                    )
                ).scalars().all()),
                notes=f"从 {success} 个历史标书自动学习，{total_chunks} 个文本块",
            )
            session.add(tpl)
            templates_extracted += 1

        # 3. 更新 run
        run.status = "success" if failed == 0 else ("success" if success > 0 else "failed")
        run.success_files = success
        run.failed_files = failed
        run.total_chunks = total_chunks
        run.templates_extracted = templates_extracted
        run.finished_at = datetime.utcnow()
        await session.commit()

        return {
            "run_id": run_id,
            "status": run.status,
            "total_files": run.total_files,
            "success_files": success,
            "failed_files": failed,
            "total_chunks": total_chunks,
            "templates_extracted": templates_extracted,
        }

    def stats(self, session: AsyncSession, tenant_id: int) -> Dict[str, Any]:
        """同步版本的统计查询（用于 API）。"""
        # 同步 vs async 共用一个 session 比较麻烦，这里用 sync 简化为 new session
        # 实际 router 调用时用 session_scope
        return {
            "tenant_id": tenant_id,
            "note": "use async stats() instead",
        }

    async def stats_async(self, session: AsyncSession, tenant_id: int) -> Dict[str, Any]:
        kb = self._kb_for(tenant_id)
        runs = (
            await session.execute(
                select(KnowledgeBootstrapRun)
                .where(KnowledgeBootstrapRun.tenant_id == tenant_id)
                .order_by(KnowledgeBootstrapRun.id.desc())
                .limit(1)
            )
        ).scalars().all()
        docs = (
            await session.execute(
                select(KnowledgeDocument).where(KnowledgeDocument.tenant_id == tenant_id)
            )
        ).scalars().all()
        tpls = (
            await session.execute(
                select(FactTemplate).where(FactTemplate.tenant_id == tenant_id)
            )
        ).scalars().all()
        return {
            "tenant_id": tenant_id,
            "kb_chunks": kb.stats()["chunks"],
            "docs_total": len(docs),
            "docs_by_status": {
                s: sum(1 for d in docs if d.status == s) for s in {d.status for d in docs}
            },
            "templates": [
                {
                    "id": t.id,
                    "name": t.name,
                    "project_type": t.project_type,
                    "doc_type": t.doc_type,
                    "sample_count": t.sample_count,
                    "is_default": bool(t.is_default),
                }
                for t in tpls
            ],
            "last_run": (
                {
                    "id": runs[0].id,
                    "status": runs[0].status,
                    "total_files": runs[0].total_files,
                    "success_files": runs[0].success_files,
                    "total_chunks": runs[0].total_chunks,
                    "started_at": runs[0].started_at.isoformat() if runs[0].started_at else None,
                    "finished_at": runs[0].finished_at.isoformat() if runs[0].finished_at else None,
                }
                if runs
                else None
            ),
        }


__all__ = [
    "KnowledgeBootstrap",
    "SUPPORTED_EXTS",
    "chunk_text",
    "parse_file",
]
