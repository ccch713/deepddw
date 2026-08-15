"""插件市场元数据初始化脚本（幂等）。

扫描 plugins/*/manifest.yaml，按关键词归类，写入 plugin_market_items 表。
title = display_name || name；installs=0；stars=0；star_count=0；updated_at = manifest mtime 或今天。

用法：
    python scripts/init_plugin_meta.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# 关键词 → 分类映射
_CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("制造业", ["bid", "capa", "chem", "sop", "制造", "工厂", "设备", "quality", "spc"]),
    ("医疗", ["clinic", "dental", "口腔", "医疗", "clinical", "patient", "doctor", "informed_consent"]),
]

# 定价试点（2026-08-14 用户拍板）：目录名 → (price_cny 分, price_note)
# 0 = 不公开/不挂价；问渠独立收费体系，钱包增值包功能不公开
_PRICING: dict[str, tuple[float, str]] = {
    "ddw_wenqu_tutor": (0.0, "问渠独立收费体系，不与 DDW 混用"),
    "ddw_clinic_cs": (99900.0, "口腔门诊包：999元/年/医生；预约短信通知SMS照实收取"),
    "ddw_esg_report": (100000.0, "ESG报告：¥1,000/份；年费 ¥6,800/年"),
    "ddw_bid_writer": (990.0, "招投标助手：¥9.9/份/次；¥99/月/15次"),
    "ddw_wallet": (0.0, "钱包增值包功能不公开（定制咨询）"),
}


def _classify(name: str, description: str = "") -> str:
    """根据插件目录名+描述关键词归类。"""
    combined = (name + " " + description).lower()
    for category, keywords in _CATEGORY_RULES:
        for kw in keywords:
            if kw in combined:
                return category
    return "通用"


async def main() -> None:
    import yaml

    from core.database.models import PluginMarketItem
    from core.database.session import init_db, session_scope
    from core.database.tenant_filter import bypass_tenant_filter

    from sqlalchemy import select

    await init_db()

    plugins_dir = _ROOT / "plugins"
    if not plugins_dir.is_dir():
        print("plugins/ 目录不存在")
        return

    added = 0
    updated = 0

    async with session_scope() as session, bypass_tenant_filter():
        for manifest_path in sorted(plugins_dir.glob("*/manifest.yaml")):
            dir_name = manifest_path.parent.name
            if dir_name in {"_template", "embedded_llm"}:
                continue

            try:
                m = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            except Exception:
                m = {}

            title = m.get("display_name") or m.get("name") or dir_name
            description = m.get("description") or ""
            category = _classify(dir_name, description)

            # updated_at: manifest mtime 或 version_date 或今天
            mtime = manifest_path.stat().st_mtime
            updated_at = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")

            existing = (
                await session.execute(
                    select(PluginMarketItem).where(PluginMarketItem.plugin_name == dir_name)
                )
            ).scalar_one_or_none()

            if existing is None:
                session.add(PluginMarketItem(
                    plugin_name=dir_name,
                    title=title,
                    category=category,
                    installs=0,
                    stars=0.0,
                    star_count=0,
                    updated_at=updated_at,
                    price_cny=_PRICING.get(dir_name, (0.0, ""))[0],
                    price_note=_PRICING.get(dir_name, (0.0, ""))[1],
                ))
                added += 1
            else:
                existing.title = title
                existing.category = category
                existing.updated_at = updated_at
                price = _PRICING.get(dir_name)
                if price:  # 有定价的插件：刷新价格（幂等）
                    existing.price_cny = price[0]
                    existing.price_note = price[1]
                updated += 1

        await session.commit()

    print(f"✅ 插件市场元数据初始化完成：新增 {added}，更新 {updated}")


if __name__ == "__main__":
    asyncio.run(main())
