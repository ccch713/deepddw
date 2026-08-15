"""DDW 文档库 URL 级保护（签名 URL + Bearer JWT 双通道鉴权）。

端点：
- ``GET /docs/fde/{filename}``  签名 URL 或 Bearer admin token 访问 FDE 内部文档
- ``GET /api/v1/docs/sign``    管理员生成签名 URL
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from core.constants.roles import ADMIN_ROLES

from core.auth.jwt import current_admin

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# 签名密钥
# ---------------------------------------------------------------------------

_sign_secret = os.environ.get("DDW_DOCS_SIGN_SECRET")
if not _sign_secret:
    _sign_secret = secrets.token_hex(32)
    logger.warning("DDW_DOCS_SIGN_SECRET 未设置，使用随机密钥（重启后旧链接失效）")

# ---------------------------------------------------------------------------
# 白名单 & 路径
# ---------------------------------------------------------------------------

_FILENAME_RE = re.compile(r"^[a-zA-Z0-9_-]+\.html$")
_SIGN_PATH_RE = re.compile(r"^[a-zA-Z0-9_/-]+\.html$")

_DOCS_ROOT = Path(__file__).resolve().parent.parent.parent / "frontend" / "docs" / "fde"


def _compute_sig(filename: str, exp: int) -> str:
    return hmac.new(
        _sign_secret.encode(), f"{filename}:{exp}".encode(), hashlib.sha256
    ).hexdigest()


# ---------------------------------------------------------------------------
# GET /docs/fde/{filename}  —— 签名 URL 或 Bearer admin token
# ---------------------------------------------------------------------------


@router.get("/docs/fde/{filename}")
async def serve_fde_doc(request: Request, filename: str):
    """FDE 内部文档访问（签名 URL 或 admin JWT 鉴权）。"""
    # 白名单校验
    if not _FILENAME_RE.fullmatch(filename):
        raise HTTPException(status_code=400, detail="非法文件名")

    # 鉴权通道 1：Bearer admin token
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        from core.auth.jwt import decode_token

        token = auth_header[7:]
        try:
            payload = decode_token(token)
            if payload.get("role") in ADMIN_ROLES:
                path = _DOCS_ROOT / filename
                if not path.is_file():
                    raise HTTPException(status_code=404, detail="文档不存在")
                return FileResponse(str(path), media_type="text/html")
        except HTTPException:
            pass  # fall through to sig check

    # 鉴权通道 2：签名 URL
    sig = request.query_params.get("sig")
    exp_str = request.query_params.get("exp")
    if not sig or not exp_str:
        raise HTTPException(status_code=401, detail="无效或过期的文档链接")

    try:
        exp = int(exp_str)
    except ValueError:
        raise HTTPException(status_code=401, detail="无效或过期的文档链接")

    if exp < int(time.time()):
        raise HTTPException(status_code=401, detail="无效或过期的文档链接")

    expected = _compute_sig(filename, exp)
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=401, detail="无效或过期的文档链接")

    path = _DOCS_ROOT / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文档不存在")

    return FileResponse(str(path), media_type="text/html")


# ---------------------------------------------------------------------------
# GET /api/v1/docs/sign  —— 管理员生成签名 URL
# ---------------------------------------------------------------------------


@router.get("/api/v1/docs/sign")
async def sign_doc_url(
    path: str = Query(..., description="文档路径，如 fde/unlimited-ocr-demo-sop.html"),
    _admin: dict = Depends(current_admin),
):
    """管理员生成签名文档 URL（有效期 900 秒）。"""
    if not _SIGN_PATH_RE.fullmatch(path):
        raise HTTPException(status_code=400, detail="非法文档路径")

    # 只允许 fde/ 前缀
    if not path.startswith("fde/"):
        raise HTTPException(status_code=403, detail="仅允许 fde/ 前缀的文档")

    basename = path.split("/")[-1]
    exp = int(time.time()) + 900
    sig = _compute_sig(basename, exp)

    return {"url": f"/docs/fde/{basename}?sig={sig}&exp={exp}"}


__all__ = ["router"]
