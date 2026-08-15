"""文档解析：md/txt/json/yaml + PDF（pymupdf，可选）。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

SUPPORTED_EXTS = {".md", ".markdown", ".txt", ".json", ".yaml", ".yml", ".pdf"}


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
            except Exception as e:
                return "", f"decode failed: {e}"

    if ext == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return json.dumps(data, ensure_ascii=False, indent=2), None
        except Exception as e:
            return "", f"json parse failed: {e}"

    if ext in {".yaml", ".yml"}:
        try:
            import yaml
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            return yaml.safe_dump(data, allow_unicode=True, sort_keys=False), None
        except Exception as e:
            return "", f"yaml parse failed: {e}"

    if ext == ".pdf":
        return _parse_pdf(path)

    return "", f"unsupported extension: {ext}"


def _parse_pdf(path: Path) -> Tuple[str, Optional[str]]:
    """PDF 解析（pymupdf），安装失败时降级。"""
    try:
        import pymupdf
        doc = pymupdf.open(str(path))
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        if text.strip():
            return text.strip(), None
        return "", "PDF contains no extractable text (scanned?)"
    except ImportError:
        return "", (
            f"PDF 解析需要 pymupdf，请安装后重试。"
            f"文件名：{path.name}"
        )
    except Exception as e:
        return "", f"pdf parse failed: {e}"


def parse_bytes(filename: str, data: bytes) -> Tuple[str, Optional[str]]:
    """从字节流解析（用于上传场景）。"""
    import tempfile

    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTS:
        return "", f"unsupported extension: {suffix}"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(data)
        tmp_path = Path(f.name)

    try:
        return parse_file(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


__all__ = ["parse_file", "parse_bytes", "SUPPORTED_EXTS"]
