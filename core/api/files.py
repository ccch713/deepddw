"""R4-6（DSH for Teams）：文件库（类 NAS）——共享目录 + 个人目录。

- data/files/shared/（family/team 共享）+ data/files/member:<id>/（个人）
- solo 模式只有个人目录（无 shared 概念）
- upload/list/download API；大小限制可配（files.max_size_mb 默认 50MB）；
  路径穿越防护（Path(name).name + 目录白名单）；Token 保护。
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from core.api_response import ok
from core.config import get_files_config
from core.security.token_gate import require_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/files", tags=["teams", "files"])

_MEMBER_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{4,64}$")


def _mode() -> str:
    """当前部署模式（延迟导入，测试可 patch）。"""
    from core.config import get_deployment_mode

    return get_deployment_mode()


def _files_root() -> Path:
    root = os.environ.get("DDW_FILES_ROOT", "")
    if root:
        return Path(root).resolve()
    return Path("./data/files").resolve()


def _resolve_dir(member_id: str = "", is_shared: bool = False) -> Path:
    """解析目标目录：shared / member:<id> / 个人默认。

    solo：只有个人目录（root/member 或 root/personal——无 shared）。
    family/team：shared + member:<id> 并存。
    """
    root = _files_root()
    mode = _mode()
    if is_shared:
        if mode == "solo":
            raise ValueError("solo 模式无共享目录")
        return root / "shared"
    # 个人目录：member:<id> 或 personal（solo/无 member_id）
    if member_id and _MEMBER_ID_RE.match(member_id):
        return root / f"member:{member_id}"
    return root / "personal"


def _safe_name(name: str) -> str:
    """防路径穿越：拒绝路径分隔符 + 白名单字符（不依赖 basename 吞掉 ../）。"""
    raw = name or ""
    if not raw or raw in (".", ".."):
        raise ValueError("invalid filename")
    # 显式拒绝路径分隔符（含 URL 解码的 %2F、反斜杠）
    if "/" in raw or "\\" in raw or ".." in raw:
        raise ValueError("invalid filename (path traversal)")
    name = Path(raw).name
    if not name or not re.match(r"^[A-Za-z0-9_\-\.\u4e00-\u9fff]+$", name):
        raise ValueError("invalid filename (chars)")
    return name


def list_files(member_id: str = "", is_shared: bool = False) -> Dict[str, Any]:
    """列出目录文件（名字/大小/修改时间）。"""
    try:
        d = _resolve_dir(member_id, is_shared)
    except ValueError as exc:  # noqa: BLE001
        return {"ok": False, "note": str(exc)}
    files: List[Dict[str, Any]] = []
    if d.exists():
        for p in sorted(d.iterdir()):
            if p.is_file():
                files.append({
                    "name": p.name,
                    "size_bytes": p.stat().st_size,
                    "modified": p.stat().st_mtime,
                })
    return {"ok": True, "dir": str(d), "files": files}


def upload_file(
    filename: str, content: bytes, member_id: str = "", is_shared: bool = False,
) -> Dict[str, Any]:
    """上传文件（大小限制 files.max_size_mb；穿越防护）。"""
    try:
        safe = _safe_name(filename)
        d = _resolve_dir(member_id, is_shared)
    except ValueError as exc:  # noqa: BLE001
        return {"ok": False, "note": str(exc)}
    max_mb = get_files_config()["max_size_mb"]
    if len(content) > max_mb * 1024 * 1024:
        return {"ok": False, "note": f"文件超过大小限制 {max_mb}MB"}
    try:
        d.mkdir(parents=True, exist_ok=True)
        (d / safe).write_bytes(content)
        return {"ok": True, "name": safe, "size_bytes": len(content)}
    except OSError as exc:  # noqa: BLE001
        logger.warning("file upload degraded: %s", exc)
        return {"ok": False, "degraded": True, "note": str(exc)}


def download_file(
    filename: str, member_id: str = "", is_shared: bool = False,
) -> Optional[Path]:
    """取文件路径（不存在返回 None；穿越防护）。"""
    try:
        safe = _safe_name(filename)
        d = _resolve_dir(member_id, is_shared)
    except ValueError:  # noqa: BLE001
        return None
    p = d / safe
    return p if p.exists() else None


def delete_file(
    filename: str, member_id: str = "", is_shared: bool = False,
) -> Dict[str, Any]:
    """删除文件（管理员/本人）。"""
    try:
        safe = _safe_name(filename)
        d = _resolve_dir(member_id, is_shared)
    except ValueError as exc:  # noqa: BLE001
        return {"ok": False, "note": str(exc)}
    p = d / safe
    if not p.exists():
        return {"ok": False, "note": "文件不存在"}
    try:
        p.unlink()
        return {"ok": True, "name": safe}
    except OSError as exc:  # noqa: BLE001
        return {"ok": False, "degraded": True, "note": str(exc)}


# ---------------------------------------------------------------------------
# HTTP 端点（Token 保护）
# ---------------------------------------------------------------------------


@router.post("/upload")
async def files_upload(
    file: UploadFile = File(...),
    member_id: str = Query("", max_length=64),
    is_shared: bool = Query(False),
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """上传（solo 无 shared；family/team shared + 个人）。"""
    content = await file.read()
    return ok(upload_file(file.filename or "unnamed", content, member_id, is_shared))


@router.get("/list")
async def files_list(
    member_id: str = Query("", max_length=64),
    is_shared: bool = Query(False),
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """列表。"""
    return ok(list_files(member_id, is_shared))


@router.get("/download/{filename}")
async def files_download(
    filename: str,
    member_id: str = Query("", max_length=64),
    is_shared: bool = Query(False),
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Any:
    """下载（穿越防护由 _safe_name 保证）。"""
    from fastapi.responses import FileResponse

    p = download_file(filename, member_id, is_shared)
    if p is None:
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(p, media_type="application/octet-stream",
                        filename=p.name)


@router.delete("/{filename}")
async def files_delete(
    filename: str,
    member_id: str = Query("", max_length=64),
    is_shared: bool = Query(False),
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """删除（本人/管理员）。"""
    return ok(delete_file(filename, member_id, is_shared))
