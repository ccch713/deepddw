"""混合审核：高置信自动入库 + 周审池管理 + 话术库淘汰 + 钉钉/企微 webhook 推送."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = _BASE_DIR / "scripts"
PENDING_DIR = _BASE_DIR / "pending_review"
POOL_DIR = _BASE_DIR / "evolution_pool"

CATEGORIES = [
    "presales_emotion",
    "presales_persuasion",
    "postsales_trouble",
    "postsales_complaint",
    "postsales_suggestion",
    "general_empathy",
]
MAX_PER_CATEGORY = 5

_AUTO_APPROVE_THRESHOLD = 0.9

# 分类关键词映射
_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "presales_emotion": [
        "价格", "贵", "便宜", "预算",
    ],
    "presales_persuasion": [
        "推荐", "组合", "选型", "方案", "行业",
    ],
    "postsales_trouble": [
        "报错", "怎么用", "配置", "安装", "卡", "失败",
    ],
    "postsales_complaint": [
        "投诉", "不满", "垃圾", "难用", "退",
    ],
    "postsales_suggestion": [
        "建议", "优化", "希望", "能不能",
    ],
}


def _classify_entry(
    entry: Dict[str, Any],
) -> List[str]:
    """按场景关键词将条目映射到分类名列表."""
    text = (
        entry.get("evidence", "")
        + " "
        + entry.get("summary", "")
        + " "
        + entry.get("suggestion", "")
    ).lower()

    matched: List[str] = []
    for cat, kws in _CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw in text:
                matched.append(cat)
                break
    # 无匹配的 praise → general_empathy
    if not matched and entry.get("type") == "praise":
        matched.append("general_empathy")
    return matched


def _read_scripts(category: str) -> List[Dict[str, Any]]:
    """读取某个分类的话术库."""
    p = SCRIPTS_DIR / f"{category}.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to read scripts %s: %s", p, exc)
        return []


def _write_scripts(
    category: str, items: List[Dict[str, Any]]
) -> None:
    """写入某个分类的话术库."""
    try:
        SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        p = SCRIPTS_DIR / f"{category}.json"
        p.write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("Failed to write scripts: %s", exc)


def _is_duplicate(
    items: List[Dict[str, Any]],
    new_item: Dict[str, Any],
) -> bool:
    """检查是否重复（同 session 同 evidence 或同 exemplar_qa.ai）."""
    new_evidence = new_item.get("exemplar_qa", {}).get("ai", "")
    new_session = new_item.get("source_session", "")
    for existing in items:
        # 同 session 同 evidence
        if (
            existing.get("source_session") == new_session
            and existing.get("title", "") == new_item.get("title", "")
        ):
            return True
        # 同分类已有相同 exemplar_qa.ai
        if existing.get("exemplar_qa", {}).get("ai", "") == new_evidence:
            return True
    return False


def _evict_lowest(
    items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """超 MAX_PER_CATEGORY 时按 hit_count 淘汰最低."""
    if len(items) <= MAX_PER_CATEGORY:
        return items
    items.sort(
        key=lambda x: x.get("hit_count", 0), reverse=True
    )
    return items[:MAX_PER_CATEGORY]


def process_day(date_str: str) -> None:
    """消费 evolution_pool/<date>.json，产出话术库 + 待审池 + webhook 通知."""
    try:
        pool_path = POOL_DIR / f"{date_str}.json"
        if not pool_path.exists():
            logger.warning("No pool file for %s", date_str)
            return

        entries: List[Dict[str, Any]] = json.loads(
            pool_path.read_text(encoding="utf-8")
        )

        pending_items: List[Dict[str, Any]] = []

        for entry in entries:
            try:
                etype = entry.get("type", "none")
                confidence = entry.get("confidence", 0.0)

                if etype == "praise" and confidence >= _AUTO_APPROVE_THRESHOLD:
                    # 高置信好评 → 自动入库
                    conv_user = entry.get("_conv_user", "")
                    conv_ai = entry.get("_conv_ai", "")
                    if not conv_user or not conv_ai:
                        # 缺真实对话数据，宁缺毋滥
                        continue
                    categories = _classify_entry(entry)
                    for cat in categories:
                        items = _read_scripts(cat)
                        new_item = {
                            "category": cat,
                            "title": entry.get("summary", ""),
                            "exemplar_qa": {
                                "user": conv_user,
                                "ai": conv_ai,
                            },
                            "source_session": entry.get(
                                "_session_id", ""
                            ),
                            "approved_at": date_str,
                            "hit_count": 0,
                        }
                        if not _is_duplicate(items, new_item):
                            items.append(new_item)
                            items = _evict_lowest(items)
                            _write_scripts(cat, items)

                elif etype in ("improvement", "demand"):
                    # 改进/需求 → 写入待审池
                    _write_pending(entry, date_str)
                    pending_items.append(entry)

                # 其余丢弃
            except Exception as exc:
                logger.warning(
                    "Entry processing failed: %s", exc
                )
                continue

        # 推送审核通知（有待审条目时）
        if pending_items:
            try:
                # 从条目中推断行业（默认 general）
                industry = "general"
                for item in pending_items:
                    ind = item.get("_industry", "")
                    if ind:
                        industry = ind
                        break
                _push_review_notification(pending_items, industry)
            except Exception as exc:
                logger.warning("Review notification failed: %s", exc)

    except Exception as exc:
        logger.warning("process_day failed: %s", exc)


def _write_pending(
    entry: Dict[str, Any], date_str: str
) -> None:
    """写入待审池."""
    try:
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        p = PENDING_DIR / f"{date_str}.json"
        existing: List[Dict] = []
        if p.exists():
            try:
                existing = json.loads(
                    p.read_text(encoding="utf-8")
                )
            except Exception:
                pass
        entry["_pending_id"] = (
            f"{date_str}_{len(existing):04d}"
        )
        entry["_pending_date"] = date_str
        existing.append(entry)
        p.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("Failed to write pending: %s", exc)


def weekly_review_report() -> str:
    """汇总 pending_review/ 全部待审条目 → markdown 报告."""
    try:
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        all_entries: List[Dict[str, Any]] = []
        for p in sorted(PENDING_DIR.glob("*.json")):
            try:
                entries = json.loads(
                    p.read_text(encoding="utf-8")
                )
                all_entries.extend(entries)
            except Exception as exc:
                logger.warning(
                    "Failed to read pending %s: %s", p, exc
                )

        lines = [
            "# 周审报告",
            "",
            f"生成时间：{time.strftime('%Y-%m-%d %H:%M')}",
            f"待审条目总数：{len(all_entries)}",
            "",
        ]
        for i, entry in enumerate(all_entries, 1):
            pid = entry.get("_pending_id", f"#{i}")
            etype = entry.get("type", "unknown")
            conf = entry.get("confidence", 0)
            summary = entry.get("summary", "")
            evidence = entry.get("evidence", "")
            suggestion = entry.get("suggestion", "")
            lines.append(
                f"**[{pid}]** 类型={etype}"
                f" 置信度={conf:.2f}"
            )
            lines.append(f"  摘要：{summary}")
            lines.append(f"  证据：{evidence}")
            lines.append(f"  建议：{suggestion}")
            lines.append("")

        report = "\n".join(lines)

        today = time.strftime("%Y-%m-%d")
        report_path = PENDING_DIR / f"weekly_{today}.md"
        report_path.write_text(report, encoding="utf-8")
        return report
    except Exception as exc:
        logger.warning("weekly_review_report failed: %s", exc)
        return ""


def apply_review(
    accept_ids: List[str],
    reject_ids: List[str],
) -> None:
    """接受 → 入话术库；拒绝 → 删除条目."""
    try:
        for p in sorted(PENDING_DIR.glob("*.json")):
            try:
                entries: List[Dict[str, Any]] = json.loads(
                    p.read_text(encoding="utf-8")
                )
            except Exception:
                continue

            remaining: List[Dict[str, Any]] = []
            for entry in entries:
                pid = entry.get("_pending_id", "")
                if pid in accept_ids:
                    # 入库
                    categories = _classify_entry(entry)
                    for cat in categories:
                        items = _read_scripts(cat)
                        new_item = {
                            "category": cat,
                            "title": entry.get("summary", ""),
                            "exemplar_qa": {
                                "user": entry.get(
                                    "evidence", ""
                                ),
                                "ai": entry.get(
                                    "suggestion", ""
                                ),
                            },
                            "source_session": entry.get(
                                "_session_id", ""
                            ),
                            "approved_at": time.strftime(
                                "%Y-%m-%d"
                            ),
                            "hit_count": 0,
                        }
                        if not _is_duplicate(items, new_item):
                            items.append(new_item)
                            items = _evict_lowest(items)
                            _write_scripts(cat, items)
                elif pid in reject_ids:
                    # 丢弃
                    pass
                else:
                    remaining.append(entry)

            p.write_text(
                json.dumps(
                    remaining, ensure_ascii=False, indent=2
                ),
                encoding="utf-8",
            )
    except Exception as exc:
        logger.warning("apply_review failed: %s", exc)


# ------------------------------------------------------------------ #
# 钉钉/企微 webhook 审核推送
# ------------------------------------------------------------------ #

def _load_review_channels() -> Dict[str, Dict[str, str]]:
    """从 deployment.yaml 读取 cs_evolution.review_channels 配置."""
    try:
        import yaml as _yaml
        for base in (Path.cwd(), Path(__file__).resolve().parents[2]):
            cfg = base / "config" / "deployment.yaml"
            if cfg.exists():
                d = _yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
                channels = d.get("cs_evolution", {}).get("review_channels", {})
                if channels:
                    return channels
    except Exception as exc:
        logger.warning("Failed to load review_channels: %s", exc)
    return {}


def _send_dingtalk_webhook(webhook: str, title: str, content: str, mention: str = "") -> None:
    """发送钉钉机器人 webhook 消息."""
    try:
        import urllib.request
        msg = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": content + (f"\n\n@{mention}" if mention else ""),
            },
        }
        if mention:
            msg["at"] = {"atMobiles": [], "isAtAll": False}
        data = json.dumps(msg).encode("utf-8")
        req = urllib.request.Request(
            webhook,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("errcode", 0) != 0:
                logger.warning("DingTalk webhook error: %s", result)
    except Exception as exc:
        logger.warning("DingTalk webhook failed: %s", exc)


def _send_wecom_webhook(webhook: str, content: str) -> None:
    """发送企微机器人 webhook 消息."""
    try:
        import urllib.request
        msg = {
            "msgtype": "markdown",
            "markdown": {"content": content},
        }
        data = json.dumps(msg).encode("utf-8")
        req = urllib.request.Request(
            webhook,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("errcode", 0) != 0:
                logger.warning("WeCom webhook error: %s", result)
    except Exception as exc:
        logger.warning("WeCom webhook failed: %s", exc)


def _push_review_notification(items: List[Dict[str, Any]], industry: str = "general") -> None:
    """推送审核通知到对应审核人（钉钉/企微）."""
    if not items:
        return

    channels = _load_review_channels()
    if not channels:
        return

    channel = channels.get(industry, channels.get("general", {}))
    if not channel:
        return

    platform = channel.get("platform", "")
    webhook = channel.get("webhook", "")
    if not webhook:
        return

    # 构建消息内容
    title = f"DDW 客服进化 - {industry} 行业待审通知"
    lines = [f"## {title}", "", f"待审条目数：{len(items)}", ""]
    for i, item in enumerate(items[:10], 1):  # 最多显示10条
        pid = item.get("_pending_id", f"#{i}")
        etype = item.get("type", "unknown")
        summary = item.get("summary", "")[:80]
        conf = item.get("confidence", 0)
        lines.append(f"**[{pid}]** 类型={etype} 置信度={conf:.2f}")
        lines.append(f"  摘要：{summary}")
        lines.append("")
    if len(items) > 10:
        lines.append(f"...还有 {len(items) - 10} 条待审")
    lines.append("---")
    lines.append("回复 `通过 <id>` 或 `否决 <id>` 进行审核")

    content = "\n".join(lines)

    try:
        if platform == "dingtalk":
            mention = channel.get("mention", "")
            _send_dingtalk_webhook(webhook, title, content, mention)
        elif platform in ("weixin", "wecom"):
            _send_wecom_webhook(webhook, content)
        else:
            logger.warning("Unknown review platform: %s", platform)
    except Exception as exc:
        logger.warning("Push review notification failed: %s", exc)
