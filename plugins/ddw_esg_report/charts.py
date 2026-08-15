"""Matplotlib chart generation for ESG reports.

Radar charts and bar charts for theme score visualization.
Uses the Agg (non-interactive) backend for headless operation.
"""

from __future__ import annotations

import logging
import os
import tempfile

import matplotlib

matplotlib.use("Agg")  # Non-interactive backend — must be before pyplot import

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

logger = logging.getLogger(__name__)

# ── Colour palette ──────────────────────────────────────────────────
COLORS = {
    "primary_blue": "#1E3A8A",
    "warm_orange": "#E8652A",
    "green": "#34C759",
    "blue": "#007AFF",
    "orange": "#FF9500",
    "purple": "#AF52DE",
    "red": "#FF3B30",
}

THEME_COLORS = [
    "#1E3A8A",  # primary blue
    "#34C759",  # green
    "#E8652A",  # warm orange
    "#007AFF",  # blue
    "#FF9500",  # orange
    "#AF52DE",  # purple
    "#FF3B30",  # red
]


def create_radar_chart(themes: list[dict], output_path: str | None = None) -> str:
    """Create a radar chart of theme scores.

    Args:
        themes: List of dicts with 'name' and 'score' keys.
        output_path: Path to save the image. If None, uses a temp file.

    Returns:
        Path to the saved radar chart image.
    """
    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".png", prefix="esg_radar_")
        os.close(fd)

    categories = [t["name"] for t in themes]
    values = [t["score"] for t in themes]
    N = len(categories)

    if N < 3:
        # Not enough dimensions for a radar chart — create a simple bar chart instead
        return _create_simple_bar(themes, output_path)

    angles = [n / float(N) * 2 * np.pi for n in range(N)]
    angles += angles[:1]
    values_plot = values + values[:1]

    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))

    # Plot
    ax.plot(angles, values_plot, "o-", linewidth=2, color=COLORS["primary_blue"])
    ax.fill(angles, values_plot, alpha=0.25, color=COLORS["blue"])

    # Labels
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=10)
    ax.set_ylim(0, 100)
    ax.set_title("ESG Theme Score Radar", fontsize=14, fontweight="bold", pad=20)

    # Add score annotations
    for angle, value in zip(angles[:-1], values):
        ax.annotate(
            f"{value:.0f}",
            xy=(angle, value),
            xytext=(angle, value + 6),
            ha="center",
            fontsize=9,
            fontweight="bold",
            color=COLORS["primary_blue"],
        )

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Radar chart saved to %s", output_path)
    return output_path


def create_bar_chart(
    dimensions: list[dict],
    output_path: str | None = None,
    title: str = "Dimension Analysis",
) -> str:
    """Create a horizontal bar chart for dimension scores.

    Args:
        dimensions: List of dicts with 'name' and 'score' keys.
        output_path: Path to save the image.
        title: Chart title.

    Returns:
        Path to the saved bar chart image.
    """
    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".png", prefix="esg_bar_")
        os.close(fd)

    names = [d["name"] for d in dimensions]
    scores = [d["score"] for d in dimensions]
    n = len(names)

    fig, ax = plt.subplots(figsize=(8, max(3, n * 0.8)))

    colors = [THEME_COLORS[i % len(THEME_COLORS)] for i in range(n)]
    y_pos = np.arange(n)

    bars = ax.barh(y_pos, scores, color=colors, height=0.6)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=10)
    ax.set_xlabel("Score", fontsize=11)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlim(0, 100)

    # Add value labels on bars
    for bar, score in zip(bars, scores):
        ax.text(
            bar.get_width() + 1,
            bar.get_y() + bar.get_height() / 2,
            f"{score:.0f}",
            va="center",
            fontsize=10,
            fontweight="bold",
        )

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Bar chart saved to %s", output_path)
    return output_path


def _create_simple_bar(themes: list[dict], output_path: str) -> str:
    """Fallback bar chart when there are fewer than 3 radar dimensions."""
    return create_bar_chart(themes, output_path, title="ESG Theme Scores")
