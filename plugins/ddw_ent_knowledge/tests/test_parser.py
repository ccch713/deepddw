"""测试文档解析。"""

from __future__ import annotations

import sys
from pathlib import Path


_project_root = str(Path(__file__).resolve().parents[3])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from plugins.ddw_ent_knowledge.core.document_parser import (
    parse_bytes,
    parse_file,
)


class TestParseMd:
    def test_parse_md(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("# Hello\n\n这是测试内容。\n\n## 第二节\n\n更多内容。", encoding="utf-8")
        text, err = parse_file(f)
        assert err is None
        assert "Hello" in text
        assert "测试内容" in text

    def test_parse_txt(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("plain text content", encoding="utf-8")
        text, err = parse_file(f)
        assert err is None
        assert "plain text" in text

    def test_parse_json(self, tmp_path):
        import json
        f = tmp_path / "test.json"
        f.write_text(json.dumps({"key": "value", "nested": [1, 2, 3]}), encoding="utf-8")
        text, err = parse_file(f)
        assert err is None
        assert "value" in text

    def test_unsupported_ext(self, tmp_path):
        f = tmp_path / "test.docx"
        f.write_bytes(b"fake")
        text, err = parse_file(f)
        assert err is not None
        assert "unsupported" in err

    def test_parse_bytes_md(self):
        text, err = parse_bytes("test.md", b"# Hello\n\nWorld")
        assert err is None
        assert "Hello" in text

    def test_parse_bytes_unsupported(self):
        text, err = parse_bytes("test.xyz", b"data")
        assert err is not None


class TestParsePdf:
    def test_parse_pdf_no_pymupdf(self, tmp_path):
        """PDF 解析在没有 pymupdf 时应返回错误提示。"""
        f = tmp_path / "test.pdf"
        f.write_bytes(b"%PDF-1.4 fake")
        text, err = parse_file(f)
        # 要么成功解析，要么提示安装 pymupdf
        if err:
            assert "pymupdf" in err or "pdf" in err.lower()
