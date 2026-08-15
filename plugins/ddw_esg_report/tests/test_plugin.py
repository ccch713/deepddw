"""Tests for the DDW ESG Report plugin."""

from __future__ import annotations

import os
import sys
import tempfile
import uuid

import pytest

# Add plugin parent to path for imports
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

from plugins.ddw_esg_report.charts import create_bar_chart, create_radar_chart  # noqa: E402
from plugins.ddw_esg_report.fonts import get_font_name, register_fonts  # noqa: E402
from plugins.ddw_esg_report.models import (  # noqa: E402
    MetaAnalysis,
    Recommendation,
    ReportGenerateRequest,
    ScoreLevel,
    ThemeScore,
)
from plugins.ddw_esg_report.pdf_generator import generate_pdf  # noqa: E402

# ── Test fixtures ───────────────────────────────────────────────────

@pytest.fixture
def sample_themes():
    """Sample theme scores for testing."""
    return [
        ThemeScore(id="env", name="环境", score=72, level=ScoreLevel.good, color="#34C759"),
        ThemeScore(id="soc", name="社会", score=65, level=ScoreLevel.medium, color="#007AFF"),
        ThemeScore(id="gov", name="治理", score=80, level=ScoreLevel.excellent, color="#1E3A8A"),
        ThemeScore(id="innov", name="创新", score=55, level=ScoreLevel.medium, color="#FF9500"),
        ThemeScore(id="risk", name="风险管理", score=70, level=ScoreLevel.good, color="#AF52DE"),
    ]


@pytest.fixture
def sample_request(sample_themes):
    """Complete sample report generation request."""
    return ReportGenerateRequest(
        assessment_id=str(uuid.uuid4())[:8],
        company_name="测试科技有限公司",
        assessment_date="2025-01-15",
        framework={"name": "GRI Standards"},
        overall={"score": 68.4, "level": "medium"},
        themes=sample_themes,
        framework_scores=[],
        meta_analysis=MetaAnalysis(
            average=68.4,
            balance="中等",
            std_dev=8.7,
            total_desc="总体表现中等偏上",
            dimensions=[
                {"name": "环境", "score": 72},
                {"name": "社会", "score": 65},
                {"name": "治理", "score": 80},
            ],
            weak=[
                {"name": "创新", "score": 55, "desc": "需要加强创新投入"},
            ],
        ),
        recommendations=[
            Recommendation(priority="高", text="加强环境管理体系建设", area="环境"),
            Recommendation(priority="中", text="提升社会责任报告透明度", area="社会"),
            Recommendation(priority="低", text="优化公司治理结构", area="治理"),
        ],
    )


# ── Font tests ──────────────────────────────────────────────────────

def test_font_registration():
    """Test that font registration succeeds (with fallback)."""
    result = register_fonts()
    assert result in ("ChineseFont", "Helvetica")
    assert isinstance(result, str)


def test_get_font_name():
    """Test get_font_name returns a valid name."""
    name = get_font_name()
    assert name in ("ChineseFont", "Helvetica")


# ── Chart tests ─────────────────────────────────────────────────────

def test_radar_chart_generation():
    """Test radar chart creation with valid data."""
    themes = [
        {"name": "环境", "score": 72},
        {"name": "社会", "score": 65},
        {"name": "治理", "score": 80},
        {"name": "创新", "score": 55},
        {"name": "风险管理", "score": 70},
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        output = os.path.join(tmpdir, "radar.png")
        result = create_radar_chart(themes, output)
        assert os.path.exists(result)
        assert os.path.getsize(result) > 0


def test_radar_chart_fallback_bar():
    """Test that <3 themes falls back to bar chart."""
    themes = [{"name": "A", "score": 50}, {"name": "B", "score": 70}]
    with tempfile.TemporaryDirectory() as tmpdir:
        output = os.path.join(tmpdir, "radar.png")
        result = create_radar_chart(themes, output)
        assert os.path.exists(result)


def test_bar_chart_generation():
    """Test bar chart creation."""
    dimensions = [
        {"name": "环境", "score": 72},
        {"name": "社会", "score": 65},
        {"name": "治理", "score": 80},
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        output = os.path.join(tmpdir, "bar.png")
        result = create_bar_chart(dimensions, output)
        assert os.path.exists(result)
        assert os.path.getsize(result) > 0


# ── PDF generation tests ────────────────────────────────────────────

def test_generate_report(sample_request):
    """Test full PDF report generation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = generate_pdf(sample_request, tmpdir)

        assert "report_id" in result
        assert "file_path" in result
        assert "pages" in result
        assert "file_size" in result
        assert "duration_ms" in result

        assert os.path.exists(result["file_path"])
        assert result["pages"] >= 1
        assert result["file_size"] > 0
        assert result["duration_ms"] >= 0


def test_generate_report_file_is_pdf(sample_request):
    """Test that generated file is a valid PDF."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = generate_pdf(sample_request, tmpdir)
        with open(result["file_path"], "rb") as f:
            header = f.read(5)
        assert header == b"%PDF-"


def test_generate_report_under_2mb(sample_request):
    """Test that generated PDF is under 2MB for typical reports."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = generate_pdf(sample_request, tmpdir)
        assert result["file_size"] < 2 * 1024 * 1024  # 2MB


def test_generate_report_minimal():
    """Test generation with minimal data (no meta analysis, no recs)."""
    req = ReportGenerateRequest(
        assessment_id="test-001",
        company_name="Minimal Corp",
        assessment_date="2025-01-01",
        themes=[ThemeScore(id="a", name="Theme A", score=50, level=ScoreLevel.medium)],
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        result = generate_pdf(req, tmpdir)
        assert os.path.exists(result["file_path"])
        assert result["pages"] >= 1


# ── Model validation tests ──────────────────────────────────────────

def test_theme_score_validation():
    """Test that theme score out of range is rejected."""
    with pytest.raises(Exception):
        ThemeScore(id="x", name="X", score=150, level=ScoreLevel.excellent)


def test_theme_score_min_length():
    """Test that empty themes list is rejected."""
    with pytest.raises(Exception):
        ReportGenerateRequest(
            assessment_id="x",
            company_name="X",
            assessment_date="2025-01-01",
            themes=[],
        )
