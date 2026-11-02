"""P0-3 薄版（R6）：AI 资产一键导出——ddw_assets_v1.zip。

"带走我的AI资产"（反锁定主张的产品化）：把记忆体 + 知识库打包为
与 DDW AI Hub 同构的产品中立格式：

    ddw_assets_v1.zip
    ├── manifest.json         # format / source / 资产计数
    ├── knowledge/*.json      # 每文档一 JSON（title/content/category/file_hash）
    ├── memory/entries.jsonl  # 五层记忆统一中立条目
    └── skills/               # 本产品无独立技能库（插件即技能）→ 留空

- 向量索引不搬：hash-trick/LanceDB 与 Hub 向量互不兼容，导入方按内容重建。
- 幂等键：knowledge 用 file_hash（导入侧按 title+content 判重）；memory 按 key。
- 导出动作发事件 ``assets.exported``（事件总线，审计痕）。
- 导入（含 Hub 包降级带入）见 core/api/assets_import.py。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.api_response import ok
from core.security.token_gate import require_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/assets", tags=["assets", "export"])

ASSETS_FORMAT = "ddw_assets_v1"


def _db_path() -> Path:
    from core.knowledge import _db_path as knowledge_db_path

    return knowledge_db_path()


def _export_dir() -> Path:
    """导出目录（默认 data/exports/，DDW_EXPORT_DIR 可覆盖）。"""
    root = os.environ.get("DDW_EXPORT_DIR", "")
    if root:
        return Path(root).resolve()
    return _db_path().parent / "exports"


def _app_version() -> str:
    """APP_VERSION 延迟导入（避免与 core.main 循环依赖）。"""
    try:
        from core.main import APP_VERSION

        return APP_VERSION
    except Exception:  # noqa: BLE001
        return "0.0.0-dev"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 数据收集（读侧直接 SQL，保证全量保真；写侧走 knowledge 层服务函数）
# ---------------------------------------------------------------------------


def collect_memory(workspace: str = "shared") -> List[Dict[str, Any]]:
    """五层记忆 → 统一中立条目（namespace/key/value/tags/source/created_at）。"""
    from core.knowledge import get_conn, close_conn

    entries: List[Dict[str, Any]] = []
    conn = get_conn()
    try:
        for r in conn.execute(
            "SELECT key, value, updated_at FROM memory_user "
            "WHERE workspace = ? ORDER BY key",
            (workspace,),
        ).fetchall():
            entries.append({
                "namespace": "user", "key": r["key"], "value": r["value"],
                "tags": [], "source": None, "created_at": r["updated_at"],
            })
        for r in conn.execute(
            "SELECT key, value, source, updated_at FROM memory_notes "
            "WHERE workspace = ? ORDER BY key",
            (workspace,),
        ).fetchall():
            entries.append({
                "namespace": "notes", "key": r["key"], "value": r["value"],
                "tags": [], "source": r["source"], "created_at": r["updated_at"],
            })
        for r in conn.execute(
            "SELECT log_date, content, auto, workspace FROM memory_logs "
            "WHERE workspace = ? ORDER BY log_date, rowid",
            (workspace,),
        ).fetchall():
            entries.append({
                "namespace": "logs", "key": r["log_date"], "value": r["content"],
                "tags": ["auto"] if r["auto"] else [], "source": None,
                "created_at": r["log_date"],
            })
        for r in conn.execute(
            "SELECT ref_date, content FROM memory_reflections "
            "WHERE workspace = ? ORDER BY ref_date",
            (workspace,),
        ).fetchall():
            entries.append({
                "namespace": "reflection", "key": r["ref_date"],
                "value": r["content"], "tags": [], "source": None,
                "created_at": r["ref_date"],
            })
        for r in conn.execute(
            "SELECT namespace, key, value, tags, created_at FROM memory_entries "
            "ORDER BY namespace, key",
        ).fetchall():
            try:
                tags = json.loads(r["tags"] or "[]")
            except (TypeError, ValueError):
                tags = []
            entries.append({
                "namespace": r["namespace"], "key": r["key"], "value": r["value"],
                "tags": tags, "source": None, "created_at": r["created_at"],
            })
        return entries
    finally:
        close_conn(conn)


def collect_knowledge() -> List[Dict[str, Any]]:
    """kb_documents 全量 → 中立文档 JSON（无分块：deepDDW 文档即整篇）。"""
    from core.knowledge import get_conn, close_conn

    docs: List[Dict[str, Any]] = []
    conn = get_conn()
    try:
        for r in conn.execute(
            "SELECT id, title, content, category, created_at FROM kb_documents "
            "ORDER BY id"
        ).fetchall():
            docs.append({
                "external_id": str(r["id"]),
                "title": r["title"],
                "content": r["content"],
                "category": r["category"],
                "created_at": r["created_at"],
                "file_hash": _sha256(f"{r['title']}\n{r['content']}"),
            })
        return docs
    finally:
        close_conn(conn)


# ---------------------------------------------------------------------------
# 打包
# ---------------------------------------------------------------------------


async def _publish_exported(counts: Dict[str, int], path: Path) -> None:
    """事件总线审计痕（失败不阻塞导出）。"""
    try:
        from core.events.bus import get_bus

        await get_bus().publish(
            "assets.exported",
            {"counts": counts, "file": path.name, "bytes": path.stat().st_size},
            source="assets-export",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("assets.exported publish failed: %s", exc)


def create_export(workspace: str = "shared") -> Dict[str, Any]:
    """一键导出：ddw_assets_v1.zip → data/exports/（返回文件名，不暴露绝对路径）。"""
    docs = collect_knowledge()
    mems = collect_memory(workspace)
    counts = {
        "knowledge": len(docs),
        "memory": len(mems),
        "skills": 0,   # 插件即技能，无独立技能库
        "flows": 0,    # 本产品无流程编排
    }

    out_dir = _export_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = out_dir / f"ddw-assets-{ts}.zip"
    try:
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            manifest = {
                "format": ASSETS_FORMAT,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "source": {
                    "product": "deepddw",
                    "app_version": _app_version(),
                    "workspace": workspace,
                },
                "assets": {
                    "knowledge": {"count": counts["knowledge"]},
                    "skills": {"count": 0, "note": "plugins-as-skills, not exported"},
                    "memory": {"count": counts["memory"]},
                    "flows": {"count": 0, "note": "not supported in this product"},
                },
            }
            zf.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2),
            )
            for i, doc in enumerate(docs):
                zf.writestr(
                    f"knowledge/doc-{i:05d}.json",
                    json.dumps(doc, ensure_ascii=False),
                )
            body = "\n".join(
                json.dumps(m, ensure_ascii=False) for m in mems
            )
            zf.writestr("memory/entries.jsonl", body)
        return {
            "ok": True,
            "file": dest.name,  # 仅文件名（DEF-004 口径）
            "size_bytes": dest.stat().st_size,
            "counts": counts,
            "workspace": workspace,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("assets export failed: %s", exc)
        return {"ok": False, "note": str(exc)}


def list_exports() -> Dict[str, Any]:
    """最近导出文件（最近 20 个）。"""
    out_dir = _export_dir()
    files: List[Dict[str, Any]] = []
    try:
        if out_dir.exists():
            for p in sorted(out_dir.glob("ddw-assets-*.zip"), reverse=True)[:20]:
                files.append({
                    "file": p.name,
                    "size_bytes": p.stat().st_size,
                    "created_at": p.stat().st_mtime,
                })
    except OSError as exc:  # noqa: BLE001
        logger.warning("assets list degraded: %s", exc)
        return {"results": [], "degraded": True}
    return {"results": files, "degraded": False}


# ---------------------------------------------------------------------------
# HTTP 端点
# ---------------------------------------------------------------------------


class ExportReq(BaseModel):
    workspace: str = "shared"


@router.post("/export")
async def assets_export(
    req: ExportReq | None = None,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """一键导出 AI 资产（zip 可下载、可导入 DDW AI Hub）。"""
    ws = (req.workspace if req else None) or "shared"
    result = create_export(workspace=ws)
    if result.get("ok") and "file" in result:
        await _publish_exported(
            result["counts"], _export_dir() / result["file"],
        )
    return ok(result)


@router.get("/exports")
async def assets_export_list(
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """列出最近导出包。"""
    return ok(list_exports())


@router.get("/exports/{filename}")
async def assets_export_download(
    filename: str,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Any:
    """下载导出包（Token 保护 + 防路径穿越）。"""
    from fastapi.responses import FileResponse

    safe = Path(filename).name
    if safe != filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    path = _export_dir() / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail="export not found")
    return FileResponse(
        path, media_type="application/zip", filename=safe,
    )
