"""P0：记忆/KB 迁移导入 + 开放导出。

导入格式：
- ``deepddw`` JSONL：``{"layer":"user|notes|logs|reflection","key","value","workspace"?}``
- ``generic`` JSONL：``{"key","value","tags"?}`` → memory_entries
- ``markdown``：Claude MEMORY.md / 笔记导出（``## 标题`` 或 ``- key: value``）

导出：
- JSONL（分层记忆）
- Markdown（可读）
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core.api_response import fail, ok
from core.privacy import is_incognito
from core.security.token_gate import require_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/migration", tags=["migration", "export"])

_LAYER_ALLOWED = {"user", "notes", "logs", "reflection", "entries"}


class ImportPayload(BaseModel):
    format: str = Field("deepddw", description="deepddw|generic|markdown")
    content: str = Field(..., min_length=1, max_length=8_000_000)
    workspace: str = Field("shared", max_length=32)
    namespace: str = Field("imported", max_length=64)
    dry_run: bool = False
    session_id: Optional[str] = None


def _parse_jsonl(content: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _parse_markdown(content: str) -> List[Dict[str, Any]]:
    """MEMORY.md / 笔记：``## 标题`` 分段，正文作 value；或 ``- key: value``。"""
    rows: List[Dict[str, Any]] = []
    section_title = ""
    section_buf: List[str] = []

    def _flush() -> None:
        nonlocal section_buf, section_title
        body = "\n".join(section_buf).strip()
        if section_title and body:
            rows.append({"layer": "notes", "key": section_title, "value": body})
        section_buf = []

    kv_re = re.compile(r"^[-*]\s+([^:：]{1,120})\s*[:：]\s*(.+)$")
    for raw in content.splitlines():
        line = raw.rstrip()
        if re.match(r"^#{1,3}\s+", line):
            _flush()
            section_title = re.sub(r"^#{1,3}\s+", "", line).strip()[:120]
            continue
        m = kv_re.match(line.strip())
        if m and not section_title:
            rows.append({
                "layer": "user",
                "key": m.group(1).strip(),
                "value": m.group(2).strip(),
            })
            continue
        if line.strip():
            section_buf.append(line)
    _flush()
    return rows


def _normalize_rows(fmt: str, content: str, default_ns: str) -> List[Dict[str, Any]]:
    fmt = (fmt or "deepddw").lower()
    if fmt == "markdown":
        raw = _parse_markdown(content)
    elif fmt in ("generic", "porter", "claude"):
        raw = _parse_jsonl(content)
        for r in raw:
            r.setdefault("layer", "entries")
    else:
        raw = _parse_jsonl(content)
    out: List[Dict[str, Any]] = []
    for r in raw:
        key = str(r.get("key") or r.get("title") or "").strip()
        value = str(r.get("value") or r.get("content") or r.get("text") or "").strip()
        if not key and not value:
            continue
        if not key:
            key = value[:48].replace("\n", " ")
        layer = str(r.get("layer") or "notes").lower()
        if layer not in _LAYER_ALLOWED:
            layer = "notes"
        out.append({
            "layer": layer,
            "key": key,
            "value": value,
            "tags": list(r.get("tags") or []),
            "workspace": str(r.get("workspace") or "").strip() or None,
            "namespace": str(r.get("namespace") or default_ns).strip() or default_ns,
            "content": value,  # logs/reflection 列名兼容
        })
    return out


def apply_import(
    rows: List[Dict[str, Any]],
    workspace: str = "shared",
    namespace: str = "imported",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """把规范化行写入对应分层表；dry_run 只计数。"""
    from core.knowledge import (
        get_conn,
        close_conn,
        memory_note_put,
        memory_user_put,
        memory_log_append,
        memory_reflect_save,
        memory_put,
    )

    counts = {"user": 0, "notes": 0, "logs": 0, "reflection": 0, "entries": 0, "skipped": 0}
    if dry_run:
        for r in rows:
            counts[r["layer"]] = counts.get(r["layer"], 0) + 1
        return {"ok": True, "dry_run": True, "counts": counts, "total": len(rows)}

    ws = workspace or "shared"
    for r in rows:
        layer = r["layer"]
        try:
            if layer == "user":
                memory_user_put(r["key"], r["value"], workspace=ws)
            elif layer == "notes":
                memory_note_put(r["key"], r["value"], source="import", workspace=ws)
            elif layer == "logs":
                memory_log_append(r["value"], workspace=ws)
            elif layer == "reflection":
                memory_reflect_save(r["value"], workspace=ws)
            else:
                memory_put(r["namespace"] or namespace, r["key"], r["value"], tags=r.get("tags"))
            counts[layer] = counts.get(layer, 0) + 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("import row failed: %s", exc)
            counts["skipped"] += 1
    return {"ok": True, "dry_run": False, "counts": counts, "total": len(rows)}


def export_memory(
    workspace: str = "shared",
    fmt: str = "jsonl",
    layers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """导出分层记忆为 JSONL 或 Markdown。"""
    from core.knowledge import (
        memory_user_list,
        memory_note_list,
        memory_logs_recent,
        memory_reflect_get,
    )

    layers = layers or ["user", "notes", "logs", "reflection"]
    payload: List[Dict[str, Any]] = []
    if "user" in layers:
        for it in memory_user_list(workspace).get("results", []):
            payload.append({"layer": "user", "key": it["key"], "value": it["value"],
                            "updated_at": it.get("updated_at"), "workspace": workspace})
    if "notes" in layers:
        for it in memory_note_list(workspace).get("results", []):
            payload.append({"layer": "notes", "key": it["key"], "value": it["value"],
                            "source": it.get("source"), "updated_at": it.get("updated_at"),
                            "workspace": workspace})
    if "logs" in layers:
        for it in memory_logs_recent(days=3650, workspace=workspace).get("results", []):
            payload.append({"layer": "logs", "key": it.get("date") or it.get("log_date") or "",
                            "value": it.get("content") or "", "workspace": workspace})
    if "reflection" in layers:
        from datetime import date

        try:
            ref = memory_reflect_get(date.today().isoformat(), workspace=workspace)
            if ref.get("found"):
                payload.append({
                    "layer": "reflection",
                    "key": ref.get("ref_date") or "reflection",
                    "value": ref.get("content") or "",
                    "workspace": workspace,
                })
        except Exception:  # noqa: BLE001
            pass

    if fmt == "markdown":
        lines = [f"# deepDDW memory export ({workspace})", ""]
        for layer in ("user", "notes", "logs", "reflection"):
            items = [p for p in payload if p["layer"] == layer]
            if not items:
                continue
            lines.append(f"## {layer}")
            lines.append("")
            for p in items:
                if layer in ("logs", "reflection"):
                    lines.append(p["value"])
                    lines.append("")
                else:
                    lines.append(f"- {p['key']}: {p['value']}")
            lines.append("")
        body = "\n".join(lines)
        return {"ok": True, "format": "markdown", "content": body, "count": len(payload)}

    body = "\n".join(json.dumps(p, ensure_ascii=False) for p in payload)
    return {"ok": True, "format": "jsonl", "content": body, "count": len(payload)}


@router.post("/import")
async def import_endpoint(
    payload: ImportPayload,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    if payload.session_id and is_incognito(payload.session_id):
        return fail("incognito session cannot import into persistent memory")
    rows = _normalize_rows(payload.format, payload.content, payload.namespace)
    if not rows:
        return fail("no importable rows found")
    result = apply_import(
        rows,
        workspace=payload.workspace,
        namespace=payload.namespace,
        dry_run=payload.dry_run,
    )
    return ok(result)


@router.post("/export")
async def export_endpoint(
    workspace: str = "shared",
    format: str = "jsonl",
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    fmt = "markdown" if format.lower() in ("md", "markdown") else "jsonl"
    return ok(export_memory(workspace=workspace, fmt=fmt))
