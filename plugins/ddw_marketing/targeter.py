"""DDW Marketing - 目标人群计算.

跨插件读 ddw_patient_crm + ddw_member_vip.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def _find(our_db: Path, name: str) -> Path | None:
    # 同 data 目录优先, 其次兄弟插件目录
    for cand in [
        our_db.parent / f"{name}.db",
        our_db.parent / f"ddw_{name}.db",
        our_db.parent.parent / f"ddw_{name}" / "data" / f"{name}.db",
        our_db.parent.parent / f"ddw_{name}" / "data" / f"ddw_{name}.db",
    ]:
        if cand.exists():
            return cand
    return None


def estimate_recipients(
    our_db: Path,
    target_tags: list[str],
    target_levels: list[str],
) -> int:
    """估算命中人数."""
    patient_db = _find(our_db, "patient_crm")
    member_db = _find(our_db, "member_vip")
    recipients: set[str] = set()
    if patient_db and target_tags:
        try:
            with sqlite3.connect(patient_db, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT id, tags FROM patients").fetchall()
            for r in rows:
                tags_raw = r["tags"]
                if not tags_raw:
                    continue
                try:
                    tags = json.loads(tags_raw)
                except json.JSONDecodeError:
                    continue
                if any(t in tags for t in target_tags):
                    recipients.add(r["id"])
        except sqlite3.Error:
            pass
    if member_db and target_levels:
        try:
            with sqlite3.connect(member_db, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT patient_id, level FROM member_accounts"
                ).fetchall()
            for r in rows:
                if r["level"] in target_levels:
                    recipients.add(r["patient_id"])
        except sqlite3.Error:
            pass
    # 没指定 tags/levels: 默认全体
    if not target_tags and not target_levels and patient_db:
        try:
            with sqlite3.connect(patient_db, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT id FROM patients").fetchall()
            for r in rows:
                recipients.add(r["id"])
        except sqlite3.Error:
            pass
    return len(recipients)
