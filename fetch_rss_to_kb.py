#!/usr/bin/env python3
"""RSS 采集入库：wewe-rss（微信公众号）→ 知识库引擎（ddw_ent_knowledge）

用法：
    python3 fetch_rss_to_kb.py [--fid-max 20] [--dry-run]
环境变量：
    WEWE_BASE   wewe-rss 地址（默认 http://192.168.1.8:4000）
    KB_BASE     知识库引擎地址（默认 http://localhost:8001）
    OUT_DIR     md 落盘目录（默认 ./rss_articles）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from xml.etree import ElementTree as ET

WEWE_BASE = os.environ.get("WEWE_BASE", "http://192.168.1.8:4000")
KB_BASE = os.environ.get("KB_BASE", "http://localhost:8001")
OUT_DIR = Path(os.environ.get("OUT_DIR", "./rss_articles"))
SEEN_FILE = OUT_DIR / "imported_links.json"


def http_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "DDW-RSS-Crawler/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def html_to_text(html: str) -> str:
    """简单 HTML → 文本（去标签、去脚本/样式、解实体）。"""
    html = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
    html = re.sub(r"(?is)<br\s*/?>", "\n", html)
    html = re.sub(r"(?is)</p>", "\n\n", html)
    html = re.sub(r"(?s)<[^>]+>", "", html)
    return unescape(re.sub(r"[ \t]+", " ", html)).strip()


def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen: set) -> None:
    SEEN_FILE.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=1))


def parse_feed(xml_bytes: bytes) -> list[dict]:
    """解析 RSS/Atom → 文章列表。"""
    root = ET.fromstring(xml_bytes)
    items = []
    # RSS 2.0
    for item in root.iter("item"):
        def g(tag: str) -> str:
            el = item.find(tag)
            return (el.text or "").strip() if el is not None else ""

        title = g("title")
        link = g("link")
        desc = g("description") or g("content:encoded") or g("encoded")
        pub = g("pubDate")
        items.append({"title": title, "link": link, "html": desc, "pub": pub})
    # Atom
    if not items:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//a:entry", ns):
            def ga(tag: str) -> str:
                el = entry.find(f"a:{tag}", ns)
                return (el.text or "").strip() if el is not None else ""

            link_el = entry.find("a:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            items.append({
                "title": ga("title"), "link": link, "html": ga("content"),
                "pub": ga("published"),
            })
    return items


def to_md(art: dict) -> str:
    text = html_to_text(art["html"])
    if not text:
        text = art["title"]
    md = (
        f"---\ntitle: {art['title']}\nsource: wewe-rss\n"
        f"url: {art['link']}\npublished: {art['pub']}\n---\n\n"
        f"# {art['title']}\n\n{text}\n"
    )
    return md


def upload_to_kb(md_content: str, fname: str) -> bool:
    """multipart 上传到知识库引擎。"""
    boundary = "----ddw" + str(int(time.time() * 1000))
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'
        "Content-Type: text/markdown\r\n\r\n"
        f"{md_content}\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{KB_BASE}/api/v1/plugins/ddw-ent-knowledge/documents/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status == 200
    except Exception as exc:  # noqa: BLE001
        print(f"    ! upload failed: {exc}")
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fid-max", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true", help="只落盘 md，不调 KB")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    seen = load_seen()
    imported = 0
    skipped = 0
    feeds_ok = 0

    for fid in range(1, args.fid_max + 1):
        url = f"{WEWE_BASE}/feeds?fid={fid}"
        try:
            xml_bytes = http_get(url, timeout=20)
        except Exception:
            continue  # 无此源
        try:
            arts = parse_feed(xml_bytes)
        except ET.ParseError:
            continue
        if not arts:
            continue
        feeds_ok += 1
        for art in arts:
            link = art["link"]
            if not link or link in seen:
                skipped += 1
                continue
            md = to_md(art)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", art["title"])[:40] or f"art_{ts}"
            fpath = OUT_DIR / f"{ts}_{fid}_{safe}.md"
            fpath.write_text(md, encoding="utf-8")
            seen.add(link)
            if not args.dry_run:
                if upload_to_kb(md, fpath.name):
                    imported += 1
                    print(f"  + [{fid}] {art['title'][:40]}")
                else:
                    skipped += 1
            else:
                imported += 1
                print(f"  + (dry) [{fid}] {art['title'][:40]}")

    save_seen(seen)
    print(f"\n完成：源 {feeds_ok} 个 | 新增 {imported} 篇 | 跳过 {skipped} 篇")
    print(f"落盘目录：{OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
