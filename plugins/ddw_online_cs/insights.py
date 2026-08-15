"""独立脚本：读对话日志 → LLM 评估 → 进化池 + 日报.

用法：python3 insights.py --date 2026-08-05 [--minimax-key env]
可被 cron 调用，全部 try/except，失败退出码 0。
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent
_LOG_DIR = _BASE_DIR / "logs"
_POOL_DIR = _BASE_DIR / "evolution_pool"
_INSIGHT_DIR = _BASE_DIR / "daily_insights"

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

_EVAL_PROMPT = (
    "你是客服对话分析师。"
    "分析下面的客户-AI客服对话，输出严格 JSON：\n"
    '{"type": "improvement|demand|praise|poor_answer|none",\n'
    ' "confidence": 0.0-1.0, "summary": "≤30字",'
    ' "evidence": "用户原话关键句",\n'
    ' "suggestion": "改进建议或新需求描述（≤50字）"}\n'
    "判定标准：\n"
    "- improvement：用户表达不满/AI答错/功能缺陷/流程卡点"
    "（如\"太慢\"\"难用\"\"报错\"\"不对\"\"失望\"）\n"
    "- demand：用户询问本产品没有的功能"
    "（如\"有没有X\"\"能不能做X\"\"你们做X吗\"）\n"
    "- praise：用户明确满意/感谢/好评"
    "（如\"谢谢\"\"很好\"\"满意\"）\n"
    "- poor_answer：AI答非所问/用户重复追问同一问题"
    "/AI回答与问题无关\n"
    "- none：普通咨询、闲聊、价格问询等无价值内容\n"
    "只输出 JSON，不要任何其他文字。"
)


# ------------------------------------------------------------------ #
# 三源 API Key 读取
# ------------------------------------------------------------------ #
def _read_api_key(cli_key: Optional[str] = None) -> str:
    """三源读取 MiniMax API key."""
    # ① 环境变量
    if cli_key:
        return cli_key
    env_key = (
        __import__("os").environ.get("DDW_MINIMAX_API_KEY", "")
    )
    if env_key:
        return env_key

    # ② config/deployment.yaml
    try:
        import yaml as _yaml
        for base in (
            Path.cwd(),
            _BASE_DIR.parents[1],
        ):
            cfg = base / "config" / "deployment.yaml"
            if cfg.exists():
                d = _yaml.safe_load(
                    cfg.read_text(encoding="utf-8")
                ) or {}
                prov = (
                    (d.get("llm") or {})
                    .get("providers", {})
                    .get("minimax", {})
                )
                k = prov.get("api_key") or ""
                if k:
                    return k
    except Exception:
        pass

    # ③ ~/.hermes/config.yaml
    try:
        import yaml as _yaml
        hermes = Path.home() / ".hermes" / "config.yaml"
        if hermes.exists():
            d = _yaml.safe_load(
                hermes.read_text(encoding="utf-8")
            ) or {}
            prov = (
                (d.get("providers") or {})
                .get("minimax-cn", {})
            )
            k = prov.get("api_key") or ""
            if k:
                return k
    except Exception:
        pass

    return ""


# ------------------------------------------------------------------ #
# JSON 解析（纯函数，可独立测试）
# ------------------------------------------------------------------ #
def _parse_eval_json(text: str) -> Optional[Dict[str, Any]]:
    """从 LLM 返回文本中解析评估 JSON，失败返回 None."""
    if not text:
        return None
    cleaned = _THINK_RE.sub("", text).strip()
    # 尝试直接解析
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # 尝试提取第一个 {...}
    m = re.search(r"\{[^{}]*\}", cleaned, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return None


def strip_think(text: str) -> str:
    """剥离 <think>...</think> 推理块."""
    if not text:
        return text
    return _THINK_RE.sub("", text).strip()


# ------------------------------------------------------------------ #
# 会话分组
# ------------------------------------------------------------------ #
def _group_sessions(
    records: List[Dict],
) -> List[List[Dict[str, str]]]:
    """按 session_id 分组还原会话（user_msg + ai_reply 配对）."""
    groups: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for r in records:
        sid = r.get("session_id", "")
        groups[sid].append(r)
    sessions: List[List[Dict[str, str]]] = []
    for sid in sorted(groups):
        msgs: List[Dict[str, str]] = []
        for rec in groups[sid]:
            if rec.get("user_msg"):
                msgs.append({
                    "role": "user",
                    "content": rec["user_msg"],
                })
            if rec.get("ai_reply"):
                msgs.append({
                    "role": "assistant",
                    "content": rec["ai_reply"],
                })
        if msgs:
            sessions.append(msgs)
    return sessions


# ------------------------------------------------------------------ #
# LLM 评估（urllib 同步调用）
# ------------------------------------------------------------------ #
def _call_llm_eval(
    messages: List[Dict[str, str]],
    api_key: str,
    api_base: str = "https://api.minimaxi.com/v1",
) -> Optional[Dict[str, Any]]:
    """调用 MiniMax-M3 评估单个会话，返回解析后的 dict 或 None."""
    conv_text = "\n".join(
        f"{m['role']}: {m['content']}" for m in messages
    )
    body = json.dumps({
        "model": "MiniMax-M3",
        "messages": [
            {"role": "system", "content": _EVAL_PROMPT},
            {"role": "user", "content": conv_text},
        ],
        "max_tokens": 3000,
        "temperature": 0.2,
    }, ensure_ascii=False).encode("utf-8")

    url = f"{api_base.rstrip('/')}/text/chatcompletion_v2"
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        choices = data.get("choices") or []
        if choices:
            c = choices[0]
            text = (
                c.get("text")
                or (c.get("message") or {}).get("content")
                or ""
            )
            return _parse_eval_json(text)
    except Exception as exc:
        logger.warning("LLM eval call failed: %s", exc)
    return None


# ------------------------------------------------------------------ #
# 日报生成
# ------------------------------------------------------------------ #
def _build_daily_report(
    date_str: str,
    results: List[Dict[str, Any]],
    mode_dist: Dict[str, int],
) -> str:
    """生成人类可读的日报 markdown."""
    improvements = [
        r for r in results if r.get("type") == "improvement"
    ]
    demands = [
        r for r in results if r.get("type") == "demand"
    ]
    praises = [
        r for r in results if r.get("type") == "praise"
    ]
    poors = [
        r for r in results if r.get("type") == "poor_answer"
    ]

    total = len(results)
    valid = len(improvements) + len(demands) + len(praises) + len(poors)

    lines = [
        f"# 客服洞察日报 {date_str}",
        "",
        (
            f"- 会话总数：{total} ｜ 有效价值：{valid} 条"
            f"（改进 {len(improvements)} /"
            f" 需求 {len(demands)} /"
            f" 好评 {len(praises)} /"
            f" 差答 {len(poors)}）"
        ),
        "",
        "## 一、产品改进点",
    ]
    for i, r in enumerate(improvements, 1):
        conf = r.get("confidence", 0)
        lines.append(
            f"{i}. [{conf:.2f}] {r.get('summary', '')}"
            f" — {r.get('evidence', '')}"
        )

    lines.append("")
    lines.append("## 二、新需求信号")
    for i, r in enumerate(demands, 1):
        conf = r.get("confidence", 0)
        lines.append(
            f"{i}. [{conf:.2f}] {r.get('summary', '')}"
            f" — {r.get('evidence', '')}"
        )

    lines.append("")
    lines.append("## 三、高满意回答（话术候选）")
    for i, r in enumerate(praises, 1):
        conf = r.get("confidence", 0)
        lines.append(
            f"{i}. [{conf:.2f}] 场景：{r.get('summary', '')}"
            f" — {r.get('evidence', '')}"
        )

    lines.append("")
    lines.append("## 四、差回答诊断")
    for i, r in enumerate(poors, 1):
        lines.append(
            f"{i}. 问题：{r.get('summary', '')}"
            f" ｜ 建议：{r.get('suggestion', '')}"
        )

    lines.append("")
    lines.append("## 五、统计")
    dist_str = " / ".join(
        f"{k}: {v}" for k, v in sorted(mode_dist.items())
    )
    lines.append(f"- 命中话术分类分布：{dist_str}")

    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ #
# 主流程
# ------------------------------------------------------------------ #
def run(date_str: str, api_key: Optional[str] = None) -> None:
    """主流程：读日志 → LLM 评估 → 输出进化池 + 日报."""
    try:
        key = _read_api_key(api_key)
        if not key:
            logger.warning("No MiniMax API key found, aborting")
            return

        # 读日志
        log_file = _LOG_DIR / f"{date_str}.jsonl"
        if not log_file.exists():
            logger.warning("No log file for %s", date_str)
            return

        records: List[Dict] = []
        try:
            with open(log_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except Exception as exc:
            logger.warning("Failed to read log: %s", exc)
            return

        if not records:
            logger.warning("Empty log for %s", date_str)
            return

        # 按 session_id 分组
        sessions = _group_sessions(records)

        # 预计算每个会话最后一条 user_msg + 对应 ai_reply
        last_pairs: List[Dict[str, str]] = []
        for sess in sessions:
            last_user = ""
            last_ai = ""
            for msg in sess:
                if msg.get("role") == "user":
                    last_user = msg.get("content", "")
                elif msg.get("role") == "assistant":
                    last_ai = msg.get("content", "")
            last_pairs.append({
                "user": last_user,
                "ai": last_ai,
            })

        # 逐会话评估
        results: List[Dict[str, Any]] = []
        mode_dist: Dict[str, int] = defaultdict(int)
        for idx, sess in enumerate(sessions):
            try:
                eval_result = _call_llm_eval(sess, key)
                if eval_result:
                    eval_result["_session_msg_count"] = len(sess)
                    # praise 条目附加真实对话
                    if eval_result.get("type") == "praise":
                        pair = last_pairs[idx]
                        if pair["user"] and pair["ai"]:
                            eval_result["_conv_user"] = pair[
                                "user"
                            ]
                            eval_result["_conv_ai"] = pair[
                                "ai"
                            ]
                    results.append(eval_result)
                    t = eval_result.get("type", "none")
                    if t != "none":
                        mode_dist[t] = mode_dist.get(t, 0) + 1
            except Exception as exc:
                logger.warning(
                    "Session eval failed: %s", exc
                )
                continue

        # 输出进化池
        _POOL_DIR.mkdir(parents=True, exist_ok=True)
        pool_path = _POOL_DIR / f"{date_str}.json"
        try:
            with open(pool_path, "w", encoding="utf-8") as f:
                json.dump(
                    results, f, ensure_ascii=False, indent=2
                )
        except Exception as exc:
            logger.warning("Failed to write pool: %s", exc)

        # 输出日报
        _INSIGHT_DIR.mkdir(parents=True, exist_ok=True)
        report = _build_daily_report(
            date_str, results, dict(mode_dist)
        )
        report_path = _INSIGHT_DIR / f"{date_str}.md"
        try:
            report_path.write_text(report, encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to write report: %s", exc)

        logger.info(
            "Insights done: %d sessions, %d results",
            len(sessions),
            len(results),
        )
    except Exception as exc:
        logger.warning("insights run failed: %s", exc)


def main() -> None:
    """CLI 入口."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="客服对话洞察分析"
    )
    parser.add_argument(
        "--date",
        default=time.strftime("%Y-%m-%d"),
        help="分析日期 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--minimax-key",
        default=None,
        help="MiniMax API key (优先级最高)",
    )
    args = parser.parse_args()
    run(args.date, args.minimax_key)
    # cron 友好：始终退出码 0
    sys.exit(0)


if __name__ == "__main__":
    main()
