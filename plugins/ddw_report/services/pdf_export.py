"""PDF 导出（占位）"""
from __future__ import annotations

from typing import Any, Dict


def export_pdf(data: Dict[str, Any], output_path: str) -> str:
    """生成 PDF 文件。生产环境用 reportlab + wqy-microhei 中文字体。"""
    # 占位实现
    return output_path
