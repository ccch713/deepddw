"""P0-3 薄版（R6）：AI 资产导入（ddw_assets_v1.zip → 本地库）。

支持两类包：
- deepDDW 导出包：换机/重装找回自己的资产；
- DDW AI Hub 导出包：降级带走（knowledge/memory 落地；skills/flows 本产品
  无对应能力，忽略并在响应中说明——"带走"是格式承诺，不是功能对齐）。

- conflict=skip（默认）：knowledge 按 title+content 判重跳过；
  conflict=overwrite：删旧（含 FTS 清理）再入。
- memory 各层按 key 幂等（logs 为 append-only，重复内容跳过；
  reflection 保留原 ref_date 直写）。
- dry_run=True 只计数不落库。
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from core.api_response import ok
from core.security.token_gate import require_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/assets", tags=["assets", "import"])


def _read_manifest(zf: ZipFile) -> Dict[str, Any]:
    try:
        return json.loads(zf.read("manifest.json").decode("utf-8"))
    except KeyError as exc:
        raise ValueError("缺少 manifest.json（不是 ddw_assets_v1 包）") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"manifest.json 解析失败: {exc}") from exc


def _kb_delete_doc(doc_id: int, title: str, content: str) -> None:
    """删旧文档（外部内容表 FTS 需 'delete' 指令同步清理）。"""
    import sqlite3

    from core.knowledge import close_conn, get_conn

    conn = get_conn()
    try:
        try:
            conn.execute(
                "INSERT INTO kb_fts(kb_fts, rowid, title, content) "
                "VALUES ('delete', ?, ?, ?)",
                (doc_id, title, content),
            )
        except sqlite3.OperationalError:
            pass  # FTS 不可用（环境未编译）——仅删主表
        conn.execute("DELETE FROM kb_documents WHERE id = ?", (doc_id,))
        conn.commit()
    finally:
        close_conn(conn)


def _import_knowledge(
    docs: List[Dict[str, Any]], conflict: str, dry_run: bool
) -> Dict[str, int]:
    from core.knowledge import close_conn, get_conn, kb_add_document

    added = skipped = 0
    conn = get_conn()
    existing: Dict[str, int] = {}
    try:
        for r in conn.execute(
            "SELECT id, title, content FROM kb_documents"
        ).fetchall():
            existing[f"{r['title']}\n{r['content']}"] = r["id"]
    finally:
        close_conn(conn)

    for doc in docs:
        title = str(doc.get("title") or "").strip()
        content = str(doc.get("content") or "")
        if not title and not content:
            continue
        dedup_key = f"{title}\n{content}"
        if dedup_key in existing:
            if conflict == "overwrite" and not dry_run:
                _kb_delete_doc(existing[dedup_key], title, content)
                kb_add_document(title, content, doc.get("category") or "public")
                added += 1
            else:
                skipped += 1
            continue
        if not dry_run:
            kb_add_document(title, content, doc.get("category") or "public")
        added += 1
    return {"added": added, "skipped": skipped}


def _import_memory(
    entries: List[Dict[str, Any]], workspace: str, dry_run: bool
) -> Dict[str, int]:
    import sqlite3

    from core.knowledge import (
        close_conn,
        get_conn,
        memory_note_put,
        memory_put,
        memory_user_put,
    )

    upserted = skipped = 0
    existing_logs = set()
    existing_reflections = set()
    conn = get_conn()
    try:
        for r in conn.execute(
            "SELECT log_date, content FROM memory_logs WHERE workspace = ?",
            (workspace,),
        ).fetchall():
            existing_logs.add(f"{r['log_date']}\n{r['content']}")
        for r in conn.execute(
            "SELECT ref_date FROM memory_reflections WHERE workspace = ?",
            (workspace,),
        ).fetchall():
            existing_reflections.add(r["ref_date"])
    finally:
        close_conn(conn)

    for e in entries:
        ns = e.get("namespace") or "entries"
        key = str(e.get("key") or "").strip()
        value = str(e.get("value") or "")
        if not value:
            continue
        if dry_run:
            upserted += 1
            continue
        try:
            if ns == "user" and key:
                memory_user_put(key, value, workspace=workspace)
            elif ns == "notes" and key:
                memory_note_put(key, value, source=e.get("source") or "import",
                                workspace=workspace)
            elif ns == "logs":
                # append-only：同日同内容判重
                log_key = f"{key or value[:10]}\n{value}"
                if log_key in existing_logs:
                    skipped += 1
                    continue
                conn = get_conn()
                try:
                    conn.execute(
                        "INSERT INTO memory_logs (log_date, content, auto, workspace) "
                        "VALUES (?, ?, ?, ?)",
                        (key or "1970-01-01", value, 0, workspace),
                    )
                    conn.commit()
                    existing_logs.add(log_key)
                finally:
                    close_conn(conn)
            elif ns == "reflection" and key:
                if key in existing_reflections:
                    skipped += 1
                    continue
                conn = get_conn()
                try:
                    conn.execute(
                        "INSERT INTO memory_reflections "
                        "(ref_date, content, style, workspace, created_at) "
                        "VALUES (?, ?, 'import', ?, datetime('now')) "
                        "ON CONFLICT(ref_date) DO UPDATE SET "
                        "content=excluded.content, workspace=excluded.workspace",
                        (key, value, workspace),
                    )
                    conn.commit()
                    existing_reflections.add(key)
                finally:
                    close_conn(conn)
            else:
                memory_put(ns or "imported", key or f"entry-{upserted}", value,
                           tags=e.get("tags"))
            upserted += 1
        except sqlite3.Error as exc:  # noqa: BLE001
            logger.warning("memory import row failed: %s", exc)
            skipped += 1
    return {"upserted": upserted, "skipped": skipped}


def import_package(
    zip_path: Path,
    workspace: str = "shared",
    conflict: str = "skip",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """导入 ddw_assets_v1.zip；返回各资产计数（ValueError=客户端错误）。"""
    if conflict not in ("skip", "overwrite"):
        raise ValueError("conflict 仅支持 skip | overwrite")
    try:
        with ZipFile(zip_path) as zf:
            names = zf.namelist()
            manifest = _read_manifest(zf)
            if manifest.get("format") != "ddw_assets_v1":
                raise ValueError(
                    f"不支持的包格式: {manifest.get('format')!r}"
                )
            docs = []
            for name in sorted(n for n in names if n.startswith("knowledge/")):
                if not name.endswith(".json"):
                    continue
                try:
                    docs.append(json.loads(zf.read(name).decode("utf-8")))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    logger.warning("skip bad knowledge entry %s: %s", name, exc)
            mem_lines = []
            if "memory/entries.jsonl" in names:
                mem_lines = [
                    ln for ln in
                    zf.read("memory/entries.jsonl").decode("utf-8").splitlines()
                    if ln.strip()
                ]
            entries = []
            for ln in mem_lines:
                try:
                    entries.append(json.loads(ln))
                except json.JSONDecodeError as exc:
                    logger.warning("skip bad memory line: %s", exc)
            skills_n = sum(
                1 for n in names if n.startswith("skills/") and not n.endswith("/")
            )
            flows_n = sum(
                1 for n in names if n.startswith("flows/") and not n.endswith("/")
            )
    except BadZipFile as exc:
        raise ValueError(f"不是有效的 zip 包: {exc}") from exc

    k_res = _import_knowledge(docs, conflict, dry_run)
    m_res = _import_memory(entries, workspace, dry_run)
    return {
        "ok": True,
        "dry_run": dry_run,
        "source": manifest.get("source", {}),
        "counts": {
            "knowledge": k_res,
            "memory": m_res,
            "skills_ignored": skills_n,
            "flows_ignored": flows_n,
        },
        "note": (
            "skills/flows 本产品无对应能力，已忽略（格式完整保留在包内）"
            if (skills_n or flows_n) else None
        ),
    }


# ---------------------------------------------------------------------------
# HTTP 端点
# ---------------------------------------------------------------------------


@router.post("/import")
async def assets_import(
    file: UploadFile = File(...),
    workspace: str = Form("shared"),
    conflict: str = Form("skip"),
    dry_run: bool = Form(False),
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """上传 ddw_assets_v1.zip 导入（deepDDW 包找回 / Hub 包降级带入）。"""
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="仅支持 .zip 资产包")
    tmp_dir = Path("/tmp") / "deepddw-assets-import"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / f"upload-{int(time.time() * 1000)}.zip"
    try:
        with open(tmp, "wb") as f:
            shutil.copyfileobj(file.file, f)
        result = import_package(
            tmp, workspace=workspace, conflict=conflict, dry_run=dry_run,
        )
        return ok(result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("assets import failed: %s", exc)
        raise HTTPException(status_code=500, detail="导入失败") from exc
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:  # noqa: BLE001
            pass
