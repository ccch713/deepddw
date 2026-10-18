"""v0.8.0（virtual-office）：虚拟办公室状态面板 API（只读聚合）。

定位：
- 把 deepDDW 各子系统的**真实活动**（设备心跳 / 对话 / 记忆写入 / 知识库入库 /
  LLM 用量）聚合为"虚拟员工在岗状态"，供 ``/ui/office.html`` 像素办公室渲染。
- **view-only**：本模块不做任何写操作、不操控任务、不透出生成内容——
  透出文本只有：固定岗位名、白名单统计短语（数量/分钟）。任何文档内容、
  记忆 value、对话原文都不出此模块（合规红线，与 DDW staffview 同构）。

虚拟员工编制（固定 8 位，前端一一对应）：
- 门卫大白（gateway）  — 设备注册/在线心跳
- 接待小深（chat）     — 对话消息量（近 24h）
- 记忆管家（memory）   — memory_entries 写入（近 24h）
- 藏书员（kb）         — kb_documents 入库（近 24h）
- 计量员（llm）        — llm_usage_records 调用/失败（近 24h）
- 蒸馏师（distill）    — 蒸馏任务（有 recent 才亮，否则待命）
- 备份员（backup）     — backups 目录最新备份时间
- 网关中继（relay）    — org_relay.db 绑定活动（近 24h）

端点（Token 门禁，向后兼容只增不改）：
- GET /api/v1/office/state → {residents, digest, banner, meta}
"""

from __future__ import annotations

import logging
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends

from core.api_response import ok
from core.security.token_gate import require_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["virtual-office"])

# 活动窗口：超过该秒数无新事件 → 员工回 idle（防"永远在打字"的假在岗）
ACTIVE_WINDOW_S = 30 * 60
# 状态聚合缓存：同一秒内多次拉取共用一份快照（大屏 + 嵌入页同开时省扫描）
_CACHE_TTL_S = 5
_cache: Dict[str, Any] = {"ts": 0.0, "data": None}


def _db_path() -> Path:
    from core.config import get_settings

    settings = get_settings()
    cfg = settings.databases.get("main", {})
    if cfg.get("engine") == "sqlite":
        return Path(cfg.get("path", "./data/ddw_main.db")).resolve()
    return Path("./data/ddw_main.db").resolve()


def _conn(path: Path | None = None) -> sqlite3.Connection:
    p = path or _db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _scalar(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> Any:
    """单值查询；表不存在/出错返回 None（办公室页面不因缺表翻车）。"""
    try:
        row = conn.execute(sql, args).fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None


def _latest(conn: sqlite3.Connection, table: str, col: str) -> str | None:
    """最近一次时间戳（文本列，YYYY-MM-DD HH:MM:SS 或 ISO）。"""
    return _scalar(conn, f"SELECT MAX({col}) FROM {table}")


def _parse_ts(v: Any) -> float | None:
    if not v:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(v)[: len(fmt) + 2], fmt).timestamp()
        except ValueError:
            continue
    return None


def _recent(conn: sqlite3.Connection, table: str, col: str, hours: float = 24) -> int:
    """近 N 小时行数（容错：时间列不可解析时退化为总数）。"""
    try:
        row = conn.execute(
            f"SELECT {col}, COUNT(*) AS n FROM {table} "
            f"WHERE {col} >= datetime('now', ?)", (f"-{int(hours)} hours",)
        ).fetchone()
        if row and row["n"]:
            return int(row["n"])
    except sqlite3.Error:
        pass
    total = _scalar(conn, f"SELECT COUNT(*) FROM {table}")
    return int(total or 0)


def office_snapshot() -> Dict[str, Any]:
    """聚合快照：固定编制 + 真实活动计数 → 前端状态机输入。"""
    now = time.time()
    if _cache["data"] is not None and now - _cache["ts"] < _CACHE_TTL_S:
        return _cache["data"]

    conn = _conn()
    residents: Dict[str, Dict[str, Any]] = {}
    digest_top: list[Dict[str, Any]] = []
    digest_fails: list[Dict[str, Any]] = []
    banner: Dict[str, Any] | None = None
    meta: Dict[str, Any] = {}

    try:  # noqa: SIM105 —— 每段独立容错，缺表/缺库都不得让面板翻车
        # —— 门卫大白：设备在线 ——
        try:
            rows = conn.execute(
                "SELECT device_id, device_name, last_seen FROM devices ORDER BY last_seen DESC"
            ).fetchall()
            online = 0
            for r in rows:
                ts = _parse_ts(r["last_seen"])
                if ts and now - ts <= 60:
                    online += 1
            total_dev = len(rows)
            if online > 0:
                residents["gateway"] = {
                    "state": "working",
                    "note": f"{online} 台设备在线",
                    "today": {"done": total_dev, "failed": 0},
                }
            else:
                residents["gateway"] = {"state": "idle", "note": "无设备在线"}
            meta["devices_online"] = online
            meta["devices_total"] = total_dev
            if total_dev:
                digest_top.append({"name": "门卫大白", "text": f"今日见过 {total_dev} 台设备，当前在线 {online} 台"})
        except sqlite3.Error:
            residents["gateway"] = {"state": "away"}

        # —— 接待小深：对话消息 ——
        try:
            n_chat = _recent(conn, "chat_messages", "created_at", 24)
            last_chat = _parse_ts(_latest(conn, "chat_messages", "created_at"))
            busy = last_chat is not None and now - last_chat <= ACTIVE_WINDOW_S
            residents["chat"] = {
                "state": "working" if busy else ("sleeping" if n_chat == 0 else "idle"),
                "note": (f"刚收到消息" if busy else (f"今日 {n_chat} 条消息" if n_chat else "今天还没人说话")),
                "today": {"done": n_chat, "failed": 0},
            }
            if n_chat:
                digest_top.append({"name": "接待小深", "text": f"今日接待 {n_chat} 条对话消息"})
        except sqlite3.Error:
            residents["chat"] = {"state": "away"}

        # —— 记忆管家：memory_entries ——
        try:
            n_mem = _recent(conn, "memory_entries", "updated_at", 24)
            last_mem = _parse_ts(_latest(conn, "memory_entries", "updated_at"))
            busy = last_mem is not None and now - last_mem <= ACTIVE_WINDOW_S
            residents["memory"] = {
                "state": "doc" if busy else "idle",
                "note": (f"正在记笔记" if busy else f"共 {conn.execute('SELECT COUNT(*) FROM memory_entries').fetchone()[0]} 条记忆"),
                "today": {"done": n_mem, "failed": 0},
            }
            if n_mem:
                digest_top.append({"name": "记忆管家", "text": f"今日整理 {n_mem} 条记忆"})
        except sqlite3.Error:
            residents["memory"] = {"state": "away"}

        # —— 藏书员：kb_documents ——
        try:
            n_kb = _recent(conn, "kb_documents", "created_at", 24)
            total_kb = _scalar(conn, "SELECT COUNT(*) FROM kb_documents") or 0
            last_kb = _parse_ts(_latest(conn, "kb_documents", "created_at"))
            busy = last_kb is not None and now - last_kb <= ACTIVE_WINDOW_S
            residents["kb"] = {
                "state": "doc" if busy else "idle",
                "note": (f"正在上架文档" if busy else f"藏书 {total_kb} 本"),
                "today": {"done": n_kb, "failed": 0},
            }
            if n_kb:
                digest_top.append({"name": "藏书员", "text": f"今日入库 {n_kb} 份文档"})
        except sqlite3.Error:
            residents["kb"] = {"state": "away"}

        # —— 计量员：llm_usage_records ——
        try:
            n_llm = _recent(conn, "llm_usage_records", "created_at", 24)
            n_fail = 0
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM llm_usage_records "
                    "WHERE created_at >= datetime('now','-24 hours') AND ok = 0"
                ).fetchone()
                n_fail = int(row[0] or 0)
            except sqlite3.Error:
                pass
            last_llm = _parse_ts(_latest(conn, "llm_usage_records", "created_at"))
            busy = last_llm is not None and now - last_llm <= ACTIVE_WINDOW_S
            residents["llm"] = {
                "state": "upset" if n_fail > 3 else ("working" if busy else "idle"),
                "note": (f"结算中" if busy else f"今日 {n_llm} 次调用"),
                "today": {"done": n_llm, "failed": n_fail},
            }
            if n_llm:
                digest_top.append({"name": "计量员", "text": f"今日 LLM 调用 {n_llm} 次" + (f"，失败 {n_fail} 次" if n_fail else "")})
            if n_fail:
                digest_fails.append({"name": "计量员", "text": f"近 24h 有 {n_fail} 次 LLM 调用失败"})
                banner = {"level": "bad", "count": n_fail, "text": "次 LLM 调用失败（近 24h），建议看下网关日志"}
        except sqlite3.Error:
            residents["llm"] = {"state": "away"}

        # —— 蒸馏师 / 备份员 / 网关中继：轻探测 ——
        residents["distill"] = {"state": "idle", "note": "待命"}
        try:
            bdir = _db_path().parent / "backups"
            if bdir.exists():
                backups = sorted(bdir.glob("*.db*"), key=lambda p: p.stat().st_mtime, reverse=True)
                if backups:
                    age_h = (now - backups[0].stat().st_mtime) / 3600
                    residents["backup"] = {
                        "state": "celebrating" if age_h < 1 else "idle",
                        "note": f"最近备份 {int(age_h)}h 前",
                    }
                    digest_top.append({"name": "备份员", "text": f"最近备份：{backups[0].name[:32]}（{int(age_h)} 小时前）"})
                else:
                    residents["backup"] = {"state": "upset", "note": "还没有备份"}
                    digest_fails.append({"name": "备份员", "text": "backups 目录为空，还没做过备份"})
            else:
                residents["backup"] = {"state": "idle", "note": "待命"}
        except OSError:
            residents["backup"] = {"state": "idle", "note": "待命"}

        try:
            relay_db = _db_path().parent / "org_relay.db"
            if relay_db.exists():
                rc = _conn(relay_db)
                try:
                    n_bind = _recent(rc, "org_bindings", "created_at", 24)
                except sqlite3.Error:
                    n_bind = 0
                finally:
                    rc.close()
                residents["relay"] = {
                    "state": "working" if n_bind else "idle",
                    "note": f"今日 {n_bind} 次绑定" if n_bind else "中继待命",
                }
            else:
                residents["relay"] = {"state": "idle", "note": "未启用"}
        except sqlite3.Error:
            residents["relay"] = {"state": "idle", "note": "未启用"}

        meta["generated_at"] = datetime.now().isoformat(timespec="seconds")
    finally:
        conn.close()

    data = {
        "residents": residents,
        "digest": {"top": digest_top[:5], "fails": digest_fails},
        "banner": banner,
        "meta": meta,
    }
    _cache["ts"], _cache["data"] = now, data
    return data


@router.get("/office/state")
async def office_state(_: Dict[str, Any] = Depends(require_access_token)):
    """虚拟办公室状态面板（只读聚合，Token 门禁）。"""
    return ok(office_snapshot())
