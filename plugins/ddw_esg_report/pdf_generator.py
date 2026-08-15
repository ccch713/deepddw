"""PDF report generation using reportlab.

Produces a multi-page A4 PDF with:
  1. Cover page — blue header, company info, score badge
  2. Score details — theme scores table with progress bars, framework table
  3. Meta analysis (optional) — 4-dimension bar chart, weakness list
  4. Radar chart — matplotlib radar of theme scores
  5. Recommendations — priority-tagged suggestions
  6. Back page — thank you, disclaimer, copyright
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

try:
    from .charts import create_bar_chart, create_radar_chart
    from .fonts import get_font_name
    from .models import ReportGenerateRequest
except ImportError:
    from charts import create_bar_chart, create_radar_chart  # type: ignore[no-redef]
    from fonts import get_font_name  # type: ignore[no-redef]
    from models import ReportGenerateRequest  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────
PAGE_WIDTH, PAGE_HEIGHT = A4  # 210mm x 297mm
MARGIN_LEFT = 15 * mm
MARGIN_RIGHT = 15 * mm
MARGIN_TOP = 15 * mm
MARGIN_BOTTOM = 20 * mm
CONTENT_WIDTH = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT  # ~180mm

# Colour palette
PRIMARY_BLUE = colors.HexColor("#1E3A8A")
WARM_ORANGE = colors.HexColor("#E8652A")
GREEN = colors.HexColor("#34C759")
BLUE = colors.HexColor("#007AFF")
ORANGE = colors.HexColor("#FF9500")
PURPLE = colors.HexColor("#AF52DE")
RED = colors.HexColor("#FF3B30")
LIGHT_GRAY = colors.HexColor("#F3F4F6")
DARK_GRAY = colors.HexColor("#374151")
WHITE = colors.white


def _build_styles(font_name: str) -> dict[str, ParagraphStyle]:
    """Build reusable paragraph styles."""
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=base["Title"],
            fontName=font_name,
            fontSize=28,
            leading=36,
            textColor=WHITE,
            alignment=TA_CENTER,
            spaceAfter=6 * mm,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=base["Normal"],
            fontName=font_name,
            fontSize=14,
            leading=20,
            textColor=colors.HexColor("#93C5FD"),
            alignment=TA_CENTER,
            spaceAfter=4 * mm,
        ),
        "h1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName=font_name,
            fontSize=20,
            leading=26,
            textColor=PRIMARY_BLUE,
            spaceBefore=8 * mm,
            spaceAfter=4 * mm,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName=font_name,
            fontSize=14,
            leading=20,
            textColor=DARK_GRAY,
            spaceBefore=4 * mm,
            spaceAfter=2 * mm,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontName=font_name,
            fontSize=10,
            leading=16,
            textColor=DARK_GRAY,
        ),
        "body_center": ParagraphStyle(
            "BodyCenter",
            parent=base["Normal"],
            fontName=font_name,
            fontSize=10,
            leading=16,
            textColor=DARK_GRAY,
            alignment=TA_CENTER,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["Normal"],
            fontName=font_name,
            fontSize=8,
            leading=12,
            textColor=colors.HexColor("#6B7280"),
        ),
        "badge_score": ParagraphStyle(
            "BadgeScore",
            parent=base["Normal"],
            fontName=font_name,
            fontSize=42,
            leading=50,
            textColor=WHITE,
            alignment=TA_CENTER,
        ),
        "badge_label": ParagraphStyle(
            "BadgeLabel",
            parent=base["Normal"],
            fontName=font_name,
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#93C5FD"),
            alignment=TA_CENTER,
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=base["Normal"],
            fontName=font_name,
            fontSize=10,
            leading=14,
            textColor=WHITE,
        ),
        "table_cell": ParagraphStyle(
            "TableCell",
            parent=base["Normal"],
            fontName=font_name,
            fontSize=9,
            leading=14,
            textColor=DARK_GRAY,
        ),
        "footer": ParagraphStyle(
            "Footer",
            parent=base["Normal"],
            fontName=font_name,
            fontSize=8,
            leading=12,
            textColor=colors.HexColor("#9CA3AF"),
            alignment=TA_CENTER,
        ),
    }


# ── Page number callback ────────────────────────────────────────────

def _add_page_number(canvas, doc):  # noqa: ANN001
    """Add page number and thin bottom line to every page."""
    page_num = canvas.getPageNumber()
    canvas.saveState()
    canvas.setStrokeColor(LIGHT_GRAY)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN_LEFT, MARGIN_BOTTOM - 5 * mm, PAGE_WIDTH - MARGIN_RIGHT, MARGIN_BOTTOM - 5 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#9CA3AF"))
    canvas.drawCentredString(PAGE_WIDTH / 2, MARGIN_BOTTOM - 10 * mm, f"— {page_num} —")
    canvas.restoreState()


# ── Section builders ────────────────────────────────────────────────

def _build_cover(styles: dict, req: ReportGenerateRequest) -> list:
    """Build cover page elements."""
    elements: list = []
    elements.append(Spacer(1, 40 * mm))

    # Title
    elements.append(Paragraph("ESG 预评估报告", styles["title"]))
    elements.append(Paragraph(f"{req.company_name}", styles["subtitle"]))
    elements.append(Paragraph(
        f"评估日期: {req.assessment_date}",
        styles["subtitle"],
    ))
    elements.append(Spacer(1, 10 * mm))

    # Score badge — large score in a coloured box
    overall = req.overall
    score_val = overall.get("score", 0) if isinstance(overall, dict) else 0
    badge_data = [
        [Paragraph(f"{score_val:.1f}", styles["badge_score"])],
        [Paragraph("Overall Score", styles["badge_label"])],
    ]
    badge_table = Table(badge_data, colWidths=[80 * mm])
    badge_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PRIMARY_BLUE),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, 0), 12 * mm),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 8 * mm),
        ("ROUNDEDCORNERS", (0, 0), (-1, -1), [4, 4, 4, 4]),
    ]))
    elements.append(badge_table)
    elements.append(Spacer(1, 10 * mm))

    # Framework info
    framework = req.framework
    if isinstance(framework, dict) and framework:
        fw_name = framework.get("name", "ESG Framework")
        elements.append(Paragraph(f"评估框架: {fw_name}", styles["body_center"]))

    elements.append(PageBreak())
    return elements


def _build_score_table(styles: dict, req: ReportGenerateRequest) -> list:
    """Build score details page with theme table and progress bars."""
    elements: list = []
    elements.append(Paragraph("评分详情", styles["h1"]))

    # ── Theme scores table ──
    header = [
        Paragraph("主题", styles["table_header"]),
        Paragraph("得分", styles["table_header"]),
        Paragraph("等级", styles["table_header"]),
        Paragraph("进度", styles["table_header"]),
    ]
    table_data = [header]

    level_labels = {
        "excellent": "优秀",
        "good": "良好",
        "medium": "中等",
        "poor": "较差",
        "fail": "不合格",
    }

    for theme in req.themes:
        # Progress bar as text (simplified visual)
        bar_len = int(theme.score / 100 * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        level_text = level_labels.get(theme.level.value if hasattr(theme.level, "value") else theme.level, theme.level)

        row = [
            Paragraph(theme.name, styles["table_cell"]),
            Paragraph(f"{theme.score:.1f}", styles["table_cell"]),
            Paragraph(level_text, styles["table_cell"]),
            Paragraph(f"<font color='{theme.color}'>{bar}</font> {theme.score:.0f}%", styles["table_cell"]),
        ]
        table_data.append(row)

    col_widths = [45 * mm, 25 * mm, 25 * mm, 85 * mm]
    score_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    score_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("ALIGN", (1, 0), (2, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
        ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
    ]))
    elements.append(score_table)
    elements.append(Spacer(1, 8 * mm))

    # ── Framework comparison table ──
    if req.framework_scores:
        elements.append(Paragraph("框架对比", styles["h2"]))
        fw_header = [
            Paragraph("框架", styles["table_header"]),
            Paragraph("得分", styles["table_header"]),
            Paragraph("满分", styles["table_header"]),
            Paragraph("得分率", styles["table_header"]),
        ]
        fw_data = [fw_header]
        for fs in req.framework_scores:
            pct = (fs.score / fs.max_score * 100) if fs.max_score > 0 else 0
            fw_data.append([
                Paragraph(fs.framework, styles["table_cell"]),
                Paragraph(f"{fs.score:.1f}", styles["table_cell"]),
                Paragraph(f"{fs.max_score:.0f}", styles["table_cell"]),
                Paragraph(f"{pct:.1f}%", styles["table_cell"]),
            ])
        fw_table = Table(fw_data, colWidths=[50 * mm, 30 * mm, 30 * mm, 30 * mm], repeatRows=1)
        fw_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
            ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
        ]))
        elements.append(fw_table)

    elements.append(PageBreak())
    return elements


def _build_meta_analysis(styles: dict, meta, chart_dir: str) -> list:
    """Build optional meta analysis page with bar chart."""
    elements: list = []
    elements.append(Paragraph("综合分析", styles["h1"]))

    # Summary text
    elements.append(Paragraph(f"平均分: {meta.average:.1f} | 标准差: {meta.std_dev:.1f} | 平衡度: {meta.balance}", styles["body"]))
    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph(meta.total_desc, styles["body"]))
    elements.append(Spacer(1, 6 * mm))

    # Bar chart
    if meta.dimensions:
        chart_path = os.path.join(chart_dir, "dimension_bar.png")
        create_bar_chart(meta.dimensions, chart_path, title="维度得分分析")
        if os.path.exists(chart_path):
            img = Image(chart_path, width=CONTENT_WIDTH, height=100 * mm)
            elements.append(img)
            elements.append(Spacer(1, 4 * mm))

    # Weaknesses
    if meta.weak:
        elements.append(Paragraph("薄弱领域", styles["h2"]))
        for item in meta.weak:
            name = item.get("name", "")
            score = item.get("score", 0)
            desc = item.get("desc", "")
            elements.append(Paragraph(
                f"<b>{name}</b> ({score:.0f}分) — {desc}",
                styles["body"],
            ))
            elements.append(Spacer(1, 2 * mm))

    elements.append(PageBreak())
    return elements


def _build_radar(styles: dict, req: ReportGenerateRequest, chart_dir: str) -> list:
    """Build radar chart page."""
    elements: list = []
    elements.append(Paragraph("主题雷达图", styles["h1"]))

    themes_for_chart = [{"name": t.name, "score": t.score} for t in req.themes]
    chart_path = os.path.join(chart_dir, "radar.png")
    create_radar_chart(themes_for_chart, chart_path)

    if os.path.exists(chart_path):
        img = Image(chart_path, width=140 * mm, height=140 * mm)
        img.hAlign = "CENTER"
        elements.append(img)

    elements.append(PageBreak())
    return elements


def _build_recommendations(styles: dict, req: ReportGenerateRequest) -> list:
    """Build recommendations page."""
    elements: list = []
    elements.append(Paragraph("改进建议", styles["h1"]))

    if not req.recommendations:
        elements.append(Paragraph("暂无建议", styles["body"]))
        elements.append(PageBreak())
        return elements

    priority_colors = {
        "高": RED,
        "中": ORANGE,
        "低": GREEN,
    }
    priority_labels = {
        "高": "高优先级",
        "中": "中优先级",
        "低": "低优先级",
    }

    for i, rec in enumerate(req.recommendations, 1):
        p_color = priority_colors.get(rec.priority, BLUE)
        p_label = priority_labels.get(rec.priority, rec.priority)
        area_text = f" | 领域: {rec.area}" if rec.area else ""

        header_text = f'<font color="{p_color.hexval()}" size="12"><b>[{p_label}]</b></font>  {rec.text}'
        elements.append(Paragraph(header_text, styles["body"]))
        if area_text:
            elements.append(Paragraph(area_text.strip(" | "), styles["small"]))
        elements.append(Spacer(1, 3 * mm))

    elements.append(PageBreak())
    return elements


def _build_back_page(styles: dict) -> list:
    """Build back page — thank you, disclaimer, copyright."""
    elements: list = []
    elements.append(Spacer(1, 60 * mm))

    elements.append(Paragraph("感谢阅读", styles["h1"]))
    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph(
        "本报告由 DDW AI Hub ESG 预评估系统自动生成。"
        "报告内容仅供参考，不构成任何法律、财务或投资建议。",
        styles["body"],
    ))
    elements.append(Spacer(1, 8 * mm))
    elements.append(Paragraph(
        "免责声明：本报告基于 AI 模型分析生成，可能包含不准确之处。"
        "请在专业顾问的指导下使用本报告。DDW AI Hub 对因使用本报告"
        "而产生的任何损失不承担责任。",
        styles["small"],
    ))
    elements.append(Spacer(1, 20 * mm))
    elements.append(Paragraph(
        f"© {datetime.now(timezone.utc).year} DDW AI Hub. All rights reserved.",
        styles["footer"],
    ))
    return elements


# ── Main generator ──────────────────────────────────────────────────

def generate_pdf(req: ReportGenerateRequest, reports_dir: str) -> dict:
    """Generate a complete ESG assessment PDF report.

    Args:
        req: The report generation request with all data.
        reports_dir: Directory to save the generated PDF.

    Returns:
        Dict with report_id, file_path, pages, file_size, duration_ms.
    """
    t0 = time.time()
    report_id = str(uuid.uuid4())[:8]

    # Ensure output directories
    os.makedirs(reports_dir, exist_ok=True)
    chart_dir = os.path.join(reports_dir, f"charts_{report_id}")
    os.makedirs(chart_dir, exist_ok=True)

    pdf_path = os.path.join(reports_dir, f"esg_report_{report_id}.pdf")

    # Register font
    font_name = get_font_name()
    styles = _build_styles(font_name)

    # Build the document
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        leftMargin=MARGIN_LEFT,
        rightMargin=MARGIN_RIGHT,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
    )

    elements: list = []

    # 1. Cover page
    elements.extend(_build_cover(styles, req))

    # 2. Score details
    elements.extend(_build_score_table(styles, req))

    # 3. Meta analysis (optional)
    if req.meta_analysis:
        elements.extend(_build_meta_analysis(styles, req.meta_analysis, chart_dir))

    # 4. Radar chart
    elements.extend(_build_radar(styles, req, chart_dir))

    # 5. Recommendations
    elements.extend(_build_recommendations(styles, req))

    # 6. Back page
    elements.extend(_build_back_page(styles))

    # Build PDF
    doc.build(elements, onFirstPage=_add_page_number, onLaterPages=_add_page_number)

    # Collect metadata
    file_size = os.path.getsize(pdf_path)
    duration_ms = int((time.time() - t0) * 1000)

    # Count pages (approximate from file — reportlab doesn't expose directly)
    # Use a simple heuristic: count form feeds or parse the PDF
    pages = _count_pdf_pages(pdf_path)

    logger.info(
        "PDF generated: %s (%d bytes, %d pages, %dms)",
        pdf_path, file_size, pages, duration_ms,
    )

    # Clean up chart temp files (not the PDF)
    try:
        import shutil
        shutil.rmtree(chart_dir, ignore_errors=True)
    except Exception:
        pass

    return {
        "report_id": report_id,
        "file_path": pdf_path,
        "file_name": os.path.basename(pdf_path),
        "pages": pages,
        "file_size": file_size,
        "duration_ms": duration_ms,
    }


def _count_pdf_pages(pdf_path: str) -> int:
    """Count pages in a PDF file by scanning for /Type /Page entries."""
    try:
        with open(pdf_path, "rb") as f:
            content = f.read()
        # Simple heuristic — count /Type /Page occurrences
        import re
        count = len(re.findall(rb"/Type\s*/Page[^s]", content))
        return max(count, 1)
    except Exception:
        return 1
