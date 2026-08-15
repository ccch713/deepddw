"""ESG benchmark mappings — 5 industry standards.

Each function maps a score (0-100) to a benchmark grade / level.
"""

from __future__ import annotations

from typing import Any


def benchmark_own(score: float) -> dict[str, str]:
    """Own rating scale: 铜/银/金/铂金/未达标."""
    if score >= 80:
        return {"level": "铂金", "label": "Platinum", "description": "行业领先"}
    if score >= 65:
        return {"level": "金牌", "label": "Gold", "description": "体系完善"}
    if score >= 45:
        return {"level": "银牌", "label": "Silver", "description": "基础合规"}
    if score >= 30:
        return {"level": "铜牌", "label": "Bronze", "description": "初步建立"}
    return {"level": "未达标", "label": "Below Bronze", "description": "尚未建立有效体系"}


def benchmark_ecovadis(score: float, theme_scores: dict[str, float]) -> dict[str, str]:
    """EcoVadis benchmark — special rules for each medal tier.

    Platinum: score >= 70 AND no dimension zero
    Gold:     score >= 58 AND all dims >= 30
    Silver:   score >= 42 AND all dims >= 20
    Bronze:   score >= 30 AND all dims >= 15
    """
    values = list(theme_scores.values()) if theme_scores else [0]

    if score >= 70 and all(v >= 0 for v in values):
        return {"level": "Platinum", "medal": "Platinum"}
    if score >= 58 and all(v >= 30 for v in values):
        return {"level": "Gold", "medal": "Gold"}
    if score >= 42 and all(v >= 20 for v in values):
        return {"level": "Silver", "medal": "Silver"}
    if score >= 30 and all(v >= 15 for v in values):
        return {"level": "Bronze", "medal": "Bronze"}
    return {"level": "Insufficient", "medal": "None"}


def benchmark_cdp(e_score: float) -> dict[str, str]:
    """CDP benchmark — E (Environmental) dimension only."""
    if e_score >= 80:
        return {"grade": "A", "label": "领导力"}
    if e_score >= 70:
        return {"grade": "A-", "label": "领导力"}
    if e_score >= 60:
        return {"grade": "B", "label": "管理"}
    if e_score >= 50:
        return {"grade": "B-", "label": "管理"}
    if e_score >= 40:
        return {"grade": "C", "label": "认知"}
    if e_score >= 30:
        return {"grade": "C-", "label": "认知"}
    if e_score >= 20:
        return {"grade": "D", "label": "披露"}
    return {"grade": "F", "label": "未参与"}


def benchmark_msci(score: float) -> dict[str, str]:
    """MSCI ESG benchmark."""
    if score >= 85:
        return {"grade": "AAA"}
    if score >= 75:
        return {"grade": "AA"}
    if score >= 65:
        return {"grade": "A"}
    if score >= 55:
        return {"grade": "BBB"}
    if score >= 45:
        return {"grade": "BB"}
    if score >= 35:
        return {"grade": "B"}
    return {"grade": "CCC"}


def benchmark_sp_csa(score: float) -> dict[str, str]:
    """S&P CSA (DJSI) benchmark."""
    if score >= 85:
        return {"rating": "Top 10%", "label": "DJSI入选"}
    if score >= 70:
        return {"rating": "Top 20%", "label": "优秀"}
    if score >= 50:
        return {"rating": "Average", "label": "中等"}
    if score >= 30:
        return {"rating": "Below Avg", "label": "待改进"}
    return {"rating": "Bottom", "label": "高风险"}


def benchmark_csi_esg(score: float) -> dict[str, str]:
    """CSI ESG benchmark (中证 ESG)."""
    if score >= 90:
        return {"grade": "AAA"}
    if score >= 80:
        return {"grade": "AA"}
    if score >= 70:
        return {"grade": "A"}
    if score >= 60:
        return {"grade": "BBB"}
    if score >= 50:
        return {"grade": "BB"}
    if score >= 40:
        return {"grade": "B"}
    if score >= 30:
        return {"grade": "CCC"}
    if score >= 20:
        return {"grade": "CC"}
    return {"grade": "C"}


def calculate_all_benchmarks(
    total_score: float,
    theme_scores: dict[str, float],
) -> dict[str, Any]:
    """Run all 5 benchmarks and return combined results.

    For CDP, uses the 'E' theme score if present, else total_score.
    """
    e_score = theme_scores.get("E", theme_scores.get("environmental", total_score))

    return {
        "own": benchmark_own(total_score),
        "ecovadis": benchmark_ecovadis(total_score, theme_scores),
        "cdp": benchmark_cdp(e_score),
        "msci": benchmark_msci(total_score),
        "sp_csa": benchmark_sp_csa(total_score),
        "csi_esg": benchmark_csi_esg(total_score),
    }
