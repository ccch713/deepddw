"""DDW 二进制文件检测（§2.6）

技术规范 v1.0 §2.6：扩展名白名单 + 内容扫描双重检测。
"""
from __future__ import annotations

from pathlib import Path

# 已知文本扩展名
_TEXT_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs",
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".json", ".yaml", ".yml", ".xml", ".toml", ".ini", ".cfg",
    ".md", ".markdown", ".rst", ".txt", ".text",
    ".csv", ".tsv", ".log",
    ".sh", ".bash", ".zsh", ".fish",
    ".sql", ".graphql", ".proto",
    ".vue", ".svelte", ".astro",
    ".java", ".kt", ".scala", ".groovy",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".hh",
    ".go", ".rs", ".rb", ".php", ".pl", ".lua",
    ".r", ".R", ".jl", ".ex", ".exs",
    ".swift", ".m", ".mm",
    ".html.erb", ".erb", ".ejs", ".hbs", ".mustache",
    ".env", ".gitignore", ".dockerignore",
})

# 已知二进制扩展名
_BINARY_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svg",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".xz",
    ".exe", ".dll", ".so", ".dylib", ".bin",
    ".mp3", ".mp4", ".wav", ".flac", ".ogg", ".avi", ".mov", ".mkv",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".pyc", ".pyo", ".class", ".o", ".obj",
})


def is_text_extension(path: str | Path) -> bool:
    """基于扩展名判断是否为文本。"""
    ext = Path(path).suffix.lower()
    return ext in _TEXT_EXTENSIONS


def is_binary_extension(path: str | Path) -> bool:
    """基于扩展名判断是否为二进制。"""
    ext = Path(path).suffix.lower()
    return ext in _BINARY_EXTENSIONS


def contains_binary_bytes(data: bytes, sample_size: int = 8192) -> bool:
    """检查数据采样是否包含 NUL 字节（典型二进制特征）。"""
    sample = data[:sample_size]
    return b"\x00" in sample


def detect_binary(path: str | Path, sample_size: int = 8192) -> bool:
    """双重检测：扩展名 + 内容采样。

    Returns:
        True = 是二进制文件
        False = 是文本文件
    """
    p = Path(path)
    ext = p.suffix.lower()

    # 优先信任扩展名
    if ext in _BINARY_EXTENSIONS:
        return True
    if ext in _TEXT_EXTENSIONS:
        return False

    # 无扩展名或未知扩展名 → 内容扫描
    try:
        with open(p, "rb") as f:
            sample = f.read(sample_size)
    except OSError:
        return False

    if not sample:
        return False  # 空文件视为文本

    return contains_binary_bytes(sample, sample_size)
