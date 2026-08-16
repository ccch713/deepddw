"""P2-1（multidevice）：备份/恢复 API——一键备份下载 + 恢复。

- 备份：把主库（ddw_main.db）用 SQLite 在线备份（.backup）到 data/backups/
  并返回下载链接；WAL 模式下安全（在线备份不损坏）。
- 恢复：上传备份文件 → 校验（SQLite 头 + integrity_check）→ 替换主库。
- 安全：备份/恢复均需 Token（管理员）；恢复会覆盖当前库（前端二次确认）。
- 每日定时备份由调用方（cron / 前端开关）触发本 API 的 schedule 参数。
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from core.api_response import ok
from core.config import get_settings
from core.security.token_gate import require_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/backup", tags=["multidevice", "backup"])

# 备份目录（默认 data/backups/）
_backup_lock = threading.Lock()


def _db_path() -> Path:
    settings = get_settings()
    cfg = settings.databases.get("main", {})
    if cfg.get("engine") == "sqlite":
        return Path(cfg.get("path", "./data/ddw_main.db")).resolve()
    return Path("./data/ddw_main.db").resolve()


def _backup_dir() -> Path:
    root = os.environ.get("DDW_BACKUP_DIR", "")
    if root:
        return Path(root).resolve()
    return _db_path().parent / "backups"


def create_backup(workspace: str = "shared") -> Dict[str, Any]:
    """执行一次备份：SQLite 在线备份 → data/backups/YYYYMMDD-HHMMSS.db。

    返回备份文件相对路径 + 大小 + 行数（可下载）。
    """
    with _backup_lock:
        db = _db_path()
        if not db.exists():
            return {"ok": False, "note": f"主库不存在: {db}"}
        bdir = _backup_dir()
        bdir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = bdir / f"deepddw-{ts}.db"
        try:
            # SQLite 在线备份（VACUUM INTO 兼容 WAL；.backup 语义）
            conn = sqlite3.connect(str(db))
            try:
                bconn = sqlite3.connect(str(dest))
                try:
                    conn.backup(bconn)
                finally:
                    bconn.close()
            finally:
                conn.close()
            size = dest.stat().st_size
            rel = dest.name  # 仅文件名（下载端点按 bdir 解析）
            return {
                "ok": True,
                "file": rel,
                "abs_path": str(dest),
                "size_bytes": size,
                "created_at": ts,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("backup failed: %s", exc)
            return {"ok": False, "degraded": True, "note": str(exc)}


def list_backups() -> Dict[str, Any]:
    """列出 data/backups/ 下最近的备份文件。"""
    bdir = _backup_dir()
    files: list[Dict[str, Any]] = []
    try:
        if bdir.exists():
            for p in sorted(bdir.glob("deepddw-*.db"), reverse=True)[:20]:
                files.append({
                    "file": p.name,
                    "size_bytes": p.stat().st_size,
                    "created_at": p.stat().st_mtime,
                })
    except OSError as exc:  # noqa: BLE001
        logger.warning("backup list degraded: %s", exc)
        return {"results": [], "degraded": True}
    return {"results": files, "degraded": False}


def restore_backup(src_path: Path) -> Dict[str, Any]:
    """恢复：校验（SQLite 头 + integrity_check）→ 替换主库（先备份现状）。

    失败保持原库不动（先复制到 .pre-restore 再替换）。
    """
    if not src_path.exists():
        return {"ok": False, "note": "备份文件不存在"}
    # 校验 SQLite 头
    with open(src_path, "rb") as f:
        head = f.read(16)
    if head[:16] != b"SQLite format 3\x00":
        return {"ok": False, "note": "不是有效的 SQLite 备份文件"}
    # integrity_check
    try:
        conn = sqlite3.connect(str(src_path))
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            if not row or row[0] != "ok":
                return {"ok": False, "note": f"完整性校验失败: {row}"}
        finally:
            conn.close()
    except sqlite3.Error as exc:  # noqa: BLE001
        return {"ok": False, "note": f"校验异常: {exc}"}

    db = _db_path()
    with _backup_lock:
        # 现状备份（防恢复失败丢数据）
        if db.exists():
            pre = db.with_suffix(db.suffix + ".pre-restore")
            try:
                shutil.copy2(db, pre)
            except OSError as exc:  # noqa: BLE001
                return {"ok": False, "note": f"现状备份失败: {exc}"}
        try:
            db.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, db)
            return {"ok": True,
                    "note": f"已恢复 {src_path.name}（原库备份为 .pre-restore）"}
        except OSError as exc:  # noqa: BLE001
            return {"ok": False, "note": f"恢复失败: {exc}"}


# ---------------------------------------------------------------------------
# HTTP 端点
# ---------------------------------------------------------------------------


class BackupReq(BaseModel):
    pass


@router.post("/create")
async def backup_now(
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """一键备份（立即执行，返回备份文件信息）。"""
    return ok(create_backup())


@router.get("/list")
async def backup_list(
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """列出最近备份。"""
    return ok(list_backups())


@router.get("/download/{filename}")
async def backup_download(
    filename: str,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Any:
    """下载备份文件（Token 保护）。"""
    from fastapi.responses import FileResponse

    bdir = _backup_dir()
    # 防路径穿越
    safe = Path(filename).name
    if safe != filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    path = bdir / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail="backup not found")
    return FileResponse(
        path, media_type="application/octet-stream",
        filename=safe,
    )


@router.post("/restore")
async def backup_restore(
    file: UploadFile = File(...),
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """恢复：上传备份文件 → 校验 → 替换主库（先备份现状）。"""
    if not file.filename or not file.filename.endswith(".db"):
        raise HTTPException(status_code=400, detail="仅支持 .db 备份文件")
    tmp = _backup_dir() / f"upload-{int(time.time())}.db"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(tmp, "wb") as f:
            shutil.copyfileobj(file.file, f)
        result = restore_backup(tmp)
        if not result.get("ok"):
            raise HTTPException(status_code=500, detail=result.get("note", "恢复失败"))
        return ok(result)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:  # noqa: BLE001
            pass
