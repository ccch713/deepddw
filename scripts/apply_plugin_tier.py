#!/usr/bin/env python3
"""批量给插件 manifest.yaml 补写 tier 字段（阶段 2-2 落地机制）。

分级依据：docs/DDW_插件分级规范_v1.0.md（核心29/实验58/废弃7）
用法: python3 scripts/apply_plugin_tier.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PLUGINS_ROOT = Path(__file__).resolve().parent.parent / "plugins"

# tier-core（29）：平台底座 + 三链
CORE = {
    # 平台底座 9
    "ddw_memory", "ddw_memory_knowledge_bridge", "ddw_llm_gateway_plugin",
    "ddw_social_login", "ddw_authz", "ddw_token_manager_plugin", "ddw_org",
    "ddw_docs_portal", "ddw_connector",
    # 链1 获客 6
    "ddw_lead_claim", "ddw_opportunity", "ddw_quotation", "ddw_contract_core",
    "ddw_signature_adapter", "ddw_order",
    # 链2 履约 8
    "ddw_instance_binding", "ddw_license_core", "ddw_wallet", "ddw_offline_pos",
    "ddw_reconciliation", "ddw_invoice", "ddw_receivable", "ddw_partner_directory",
    # 链3 服务 6
    "ddw_support_ticket", "ddw_online_cs", "ddw_followup", "ddw_knowledge_hierarchy",
    "ddw_ent_knowledge", "ddw_renewal",
}

# tier-archive：归档目录（_archived/ 下，不处理 manifest——已在 norecursedirs）
ARCHIVED = {
    "ddw_email_assistant", "ddw_llm_gateway", "ddw_smart_cs", "ddw_token_manager",
    "customer_service", "ddw_aggregated_pay",
}


def tier_of(plugin: str) -> str:
    if plugin in CORE:
        return "core"
    if plugin in ARCHIVED:
        return "archive"
    return "beta"


def apply(dry_run: bool) -> None:
    updated, skipped, missing = 0, 0, 0
    for mf in sorted(PLUGINS_ROOT.glob("*/manifest.yaml")):
        plugin_dir = mf.parent.name
        if plugin_dir.startswith("_"):
            continue
        tier = tier_of(plugin_dir)
        src = mf.read_text(encoding="utf-8")
        if re.search(r"^tier:\s*\S+", src, re.MULTILINE):
            skipped += 1
            continue
        # 在 name 行后插入 tier
        new_src = re.sub(
            r"(^name:\s*\S+\n)",
            rf"\1tier: {tier}\n",
            src, count=1, flags=re.MULTILINE,
        )
        if new_src == src:
            missing += 1
            print(f"⚠️ 无法定位 name 行: {mf}")
            continue
        if dry_run:
            print(f"[dry-run] {plugin_dir}: tier={tier}")
        else:
            mf.write_text(new_src, encoding="utf-8")
            print(f"✅ {plugin_dir}: tier={tier}")
        updated += 1
    print(f"--- 完成: 更新 {updated} / 跳过 {skipped} / 异常 {missing}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    apply(args.dry_run)
    sys.exit(0)
