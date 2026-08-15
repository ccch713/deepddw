"""皮肤商店服务（2026-08-14 移植自 wenquK12 skin.html）。

预设皮肤 css_vars 使用学习台 CSS 变量体系
（--bg/--sidebar/--sidebar-text/--card/--text/--text-dim/--accent/--gold/--line/--shadow），
与紫色版 PWA 皮肤系统（SKINS 对象）同构，激活后前端直接注入生效。

皮肤市场规则（用户拍板）：
- 官方皮肤免费；UGC 定价上限 5 元，建议 1-3 元
- 售卖 T+0，作者 75% / 平台 25%（含个税代扣）——M1 钱包结算
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wenqu_tutor.models import (
    WenquTheme,
    WenquUserTheme,
)

# ── 预设皮肤（官方免费，css_vars 适配学习台变量体系） ──
PRESET_THEMES = [
    {
        "name": "朱砂经典",
        "description": "问渠默认配色，新中式书院风",
        "target_gender": "unisex",
        "style_tags": ["新中式", "简约", "经典"],
        "css_vars": {
            "--bg": "#F7F1E3", "--sidebar": "#8C2E24",
            "--sidebar-text": "#FDF6E3", "--sidebar-active": "rgba(255,255,255,0.16)",
            "--card": "#FDF9F0", "--text": "#3A3A3A", "--text-dim": "#8A7F6E",
            "--accent": "#B03A2E", "--gold": "#E8C46B",
            "--line": "rgba(176,58,46,0.16)", "--shadow": "0 2px 8px rgba(0,0,0,0.08)",
        },
    },
    {
        "name": "樱花粉",
        "description": "温柔粉色系，适合女生",
        "target_gender": "female",
        "style_tags": ["温柔", "粉色", "可爱"],
        "css_vars": {
            "--bg": "#FFF0F3", "--sidebar": "#D4576E",
            "--sidebar-text": "#FFF5F7", "--sidebar-active": "rgba(255,255,255,0.2)",
            "--card": "#FFE8EE", "--text": "#5A3A42", "--text-dim": "#A08A92",
            "--accent": "#E8839C", "--gold": "#FFB7C5",
            "--line": "rgba(232,131,156,0.18)", "--shadow": "0 2px 8px rgba(0,0,0,0.06)",
        },
    },
    {
        "name": "星空蓝",
        "description": "沉稳蓝色系，适合男生",
        "target_gender": "male",
        "style_tags": ["沉稳", "蓝色", "科技"],
        "css_vars": {
            "--bg": "#F0F4F8", "--sidebar": "#1D4D8A",
            "--sidebar-text": "#E8F0FA", "--sidebar-active": "rgba(255,255,255,0.16)",
            "--card": "#F8FAFD", "--text": "#2C3E50", "--text-dim": "#6B7C8E",
            "--accent": "#2E65A8", "--gold": "#FFA726",
            "--line": "rgba(46,101,168,0.16)", "--shadow": "0 2px 8px rgba(0,0,0,0.08)",
        },
    },
    {
        "name": "森林绿",
        "description": "自然绿色系，清新治愈",
        "target_gender": "unisex",
        "style_tags": ["自然", "绿色", "治愈"],
        "css_vars": {
            "--bg": "#F1F8E9", "--sidebar": "#1B5E20",
            "--sidebar-text": "#F4FAF0", "--sidebar-active": "rgba(255,255,255,0.16)",
            "--card": "#F6FBF0", "--text": "#3E2723", "--text-dim": "#8A7A72",
            "--accent": "#2E7D32", "--gold": "#FFC107",
            "--line": "rgba(46,125,50,0.16)", "--shadow": "0 2px 8px rgba(0,0,0,0.08)",
        },
    },
    {
        "name": "深夜紫",
        "description": "神秘紫色系，学霸风格",
        "target_gender": "unisex",
        "style_tags": ["神秘", "紫色", "学霸"],
        "css_vars": {
            "--bg": "#F3E5F5", "--sidebar": "#4A148C",
            "--sidebar-text": "#F3E8F9", "--sidebar-active": "rgba(255,255,255,0.16)",
            "--card": "#F9F3FC", "--text": "#311B92", "--text-dim": "#7C6FA8",
            "--accent": "#7B1FA2", "--gold": "#00BCD4",
            "--line": "rgba(123,31,162,0.16)", "--shadow": "0 2px 8px rgba(0,0,0,0.08)",
        },
    },
]


def generate_theme_id() -> str:
    """生成皮肤 ID：TH + 时间戳 + 随机。"""
    return f"TH{int(time.time() * 1000)}{uuid.uuid4().hex[:6]}"


async def seed_presets(db: AsyncSession) -> dict:
    """初始化预设皮肤（幂等：按 name 去重）。"""
    created = 0
    for preset in PRESET_THEMES:
        result = await db.execute(
            select(WenquTheme).where(WenquTheme.name == preset["name"])
        )
        if result.scalar_one_or_none():
            continue
        db.add(
            WenquTheme(
                id=generate_theme_id(),
                name=preset["name"],
                description=preset["description"],
                css_vars=json.dumps(preset["css_vars"], ensure_ascii=False),
                style_tags=json.dumps(preset["style_tags"], ensure_ascii=False),
                target_gender=preset["target_gender"],
                is_official=True,
                is_approved=True,
                price_cents=0,
            )
        )
        created += 1
    await db.commit()
    return {"created": created, "total_preset": len(PRESET_THEMES)}


async def list_themes(
    db: AsyncSession,
    target_gender: Optional[str] = None,
) -> tuple[list[dict], int]:
    """皮肤列表（已审核；按销量降序）。"""
    query = select(WenquTheme).where(WenquTheme.is_approved.is_(True))
    if target_gender and target_gender != "all":
        query = query.where(
            (WenquTheme.target_gender == target_gender)
            | (WenquTheme.target_gender == "unisex")
        )
    result = await db.execute(
        query.order_by(WenquTheme.sales_count.desc())
    )
    themes = result.scalars().all()
    items = [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "css_vars": json.loads(t.css_vars),
            "style_tags": json.loads(t.style_tags or "[]"),
            "target_gender": t.target_gender,
            "price_cents": t.price_cents,
            "price_yuan": t.price_cents / 100,
            "sales_count": t.sales_count,
            "is_official": t.is_official,
        }
        for t in themes
    ]
    return items, len(items)


async def get_active_theme(
    db: AsyncSession,
    student_name: str,
) -> Optional[dict]:
    """学生当前激活的皮肤（无则返回 None → 前端用默认）。"""
    result = await db.execute(
        select(WenquUserTheme)
        .where(WenquUserTheme.student_name == student_name)
        .order_by(WenquUserTheme.activated_at.desc())
        .limit(1)
    )
    ut = result.scalar_one_or_none()
    if not ut:
        return None
    theme = await db.get(WenquTheme, ut.theme_id)
    if not theme:
        return None
    return {
        "id": theme.id,
        "name": theme.name,
        "css_vars": json.loads(theme.css_vars),
    }


async def activate_theme(
    db: AsyncSession,
    student_name: str,
    theme_id: str,
) -> dict:
    """激活皮肤（记录激活流水；前端 localStorage 持久化生效）。"""
    theme = await db.get(WenquTheme, theme_id)
    if not theme or not theme.is_approved:
        raise ValueError(f"Theme {theme_id} not found or not approved")

    db.add(
        WenquUserTheme(
            student_name=student_name,
            theme_id=theme_id,
        )
    )
    # 销量 +1
    theme.sales_count += 1
    await db.commit()
    return {
        "activated": True,
        "theme_id": theme_id,
        "css_vars": json.loads(theme.css_vars),
    }


__all__ = [
    "PRESET_THEMES",
    "activate_theme",
    "generate_theme_id",
    "get_active_theme",
    "list_themes",
    "seed_presets",
]
