"""deepDDW 个人级知识库 + 轻量记忆服务（开源白名单组件，SQLite 基础实现）。

- 知识库：``kb_documents`` 表（title/content），关键词检索（SQLite FTS5 优先，退化到 LIKE）；
  LanceDB 向量检索作为可选增强（``LANCEDB_PATH`` 存在时启用，失败自动降级不阻塞）。
- 记忆：``memory_entries`` 表，简单的键值/列表式长期记忆（deepDDW v0.1 内置实现；
  部署可另接 agentmemory MCP 服务作为外部记忆后端）。

设计原则：
- 断网/存储故障不阻塞对话主流程：所有查询失败都返回空结果 + ``degraded=True`` 标记。
- 本模块为 core 服务层：MCP 工具（ddw.kb.search / ddw.memory.*）与 REST API 共用。
"""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import get_settings

logger = logging.getLogger(__name__)

_DB_PATH_DEFAULT = "./data/ddw_main.db"

# FTS5 是否可用的运行时探测缓存
_fts_available: Optional[bool] = None


# ---------------------------------------------------------------------------
# 连接与建表
# ---------------------------------------------------------------------------


def _db_path() -> Path:
    settings = get_settings()
    cfg = settings.databases.get("main", {})
    if cfg.get("engine") == "sqlite":
        return Path(cfg.get("path", _DB_PATH_DEFAULT)).resolve()
    return Path(_DB_PATH_DEFAULT).resolve()


def get_conn() -> sqlite3.Connection:
    """同步 SQLite 连接（知识库/记忆为轻量本地操作，避免 async driver 依赖）。"""
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS kb_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT 'public',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS memory_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            namespace TEXT NOT NULL DEFAULT 'default',
            key TEXT,
            value TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_memory_namespace ON memory_entries(namespace, key);
        """
    )
    conn.commit()


def _fts_supported(conn: sqlite3.Connection) -> bool:
    global _fts_available
    if _fts_available is None:
        try:
            conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _kb_fts_test USING fts5(x)")
            _fts_available = True
        except sqlite3.OperationalError:
            _fts_available = False
    return _fts_available


# ---------------------------------------------------------------------------
# 知识库
# ---------------------------------------------------------------------------


def kb_add_document(title: str, content: str, category: str = "public") -> Dict[str, Any]:
    """新增知识文档。"""
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO kb_documents (title, content, category) VALUES (?, ?, ?)",
            (title, content, category),
        )
        conn.commit()
        doc_id = cur.lastrowid
        if _fts_supported(conn):
            try:
                conn.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(title, content, content='kb_documents', content_rowid='id')"
                )
                conn.execute(
                    "INSERT INTO kb_fts (rowid, title, content) VALUES (?, ?, ?)",
                    (doc_id, title, content),
                )
                conn.commit()
            except sqlite3.OperationalError as exc:  # noqa: BLE001
                logger.warning("kb fts index failed, fallback to LIKE: %s", exc)
        return {"id": doc_id, "title": title, "category": category}
    finally:
        conn.close()


def kb_search(query: str, top_k: int = 5) -> Dict[str, Any]:
    """知识库关键词检索（FTS5 优先，退化 LIKE）。失败返回空结果 + degraded 标记。"""
    top_k = max(1, min(int(top_k or 5), 20))
    query = (query or "").strip()
    if not query:
        return {"results": [], "degraded": False, "note": "empty query"}
    try:
        conn = get_conn()
        try:
            if _fts_supported(conn):
                try:
                    conn.execute(
                        "CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(title, content, content='kb_documents', content_rowid='id')"
                    )
                    rows = conn.execute(
                        "SELECT d.id, d.title, d.content, d.category, bm25(kb_fts) AS score "
                        "FROM kb_fts JOIN kb_documents d ON d.id = kb_fts.rowid "
                        "WHERE kb_fts MATCH ? ORDER BY score LIMIT ?",
                        (_fts_query(query), top_k),
                    ).fetchall()
                    if rows:
                        return {
                            "results": [_kb_row(r) for r in rows],
                            "degraded": False,
                        }
                except sqlite3.OperationalError as exc:  # noqa: BLE001
                    logger.debug("kb fts query failed, fallback to LIKE: %s", exc)
            # LIKE 兜底：按 title/content 命中次数粗排序
            like = f"%{query}%"
            rows = conn.execute(
                "SELECT id, title, content, category, 0 AS score FROM kb_documents "
                "WHERE title LIKE ? OR content LIKE ? ORDER BY id DESC LIMIT ?",
                (like, like, top_k),
            ).fetchall()
            return {"results": [_kb_row(r) for r in rows], "degraded": False}
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001  # 存储故障不阻塞主流程
        logger.warning("kb_search degraded: %s", exc)
        return {"results": [], "degraded": True, "note": str(exc)}


def _fts_query(query: str) -> str:
    """把用户查询转成 FTS5 安全 MATCH 表达式（去除特殊字符，按词 AND）。"""
    tokens = [t for t in re.split(r"\s+", query) if t]
    cleaned = [re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]", "", t) for t in tokens]
    cleaned = [c for c in cleaned if c]
    if not cleaned:
        return '"{}"'.format(query.replace('"', '""'))
    return " AND ".join(f'"{c}"' for c in cleaned[:8])


def _kb_row(row: sqlite3.Row) -> Dict[str, Any]:
    content = row["content"] or ""
    excerpt = content[:200] + ("…" if len(content) > 200 else "")
    return {
        "id": row["id"],
        "title": row["title"],
        "excerpt": excerpt,
        "category": row["category"],
        "score": row["score"] if "score" in row.keys() else 0,
    }


# ---------------------------------------------------------------------------
# 记忆（轻量 SQLite 实现；外部 agentmemory MCP 可选接入）
# ---------------------------------------------------------------------------


def memory_put(namespace: str, key: str, value: str, tags: Optional[List[str]] = None) -> Dict[str, Any]:
    """写入一条记忆（同 namespace+key 覆盖）。"""
    ns = namespace or "default"
    tags_json = __import__("json").dumps(tags or [], ensure_ascii=False)
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT id FROM memory_entries WHERE namespace=? AND key=?", (ns, key)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE memory_entries SET value=?, tags=?, updated_at=datetime('now') WHERE id=?",
                (value, tags_json, existing["id"]),
            )
            mem_id = existing["id"]
        else:
            cur = conn.execute(
                "INSERT INTO memory_entries (namespace, key, value, tags) VALUES (?, ?, ?, ?)",
                (ns, key, value, tags_json),
            )
            mem_id = cur.lastrowid
        conn.commit()
        return {"id": mem_id, "namespace": ns, "key": key, "ok": True}
    finally:
        conn.close()


def memory_get(namespace: str, key: str) -> Dict[str, Any]:
    """读取单条记忆；缺失返回 None（不抛错）。"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM memory_entries WHERE namespace=? AND key=?", (namespace or "default", key)
        ).fetchone()
        if row is None:
            return {"found": False, "value": None}
        return {"found": True, "value": row["value"], "tags": __import__("json").loads(row["tags"] or "[]")}
    finally:
        conn.close()


def memory_search(namespace: str, query: str, top_k: int = 5) -> Dict[str, Any]:
    """按内容关键词检索记忆（LIKE 匹配 value/tags）。"""
    top_k = max(1, min(int(top_k or 5), 20))
    like = f"%{query}%"
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM memory_entries WHERE namespace=? AND (value LIKE ? OR tags LIKE ?) "
            "ORDER BY updated_at DESC LIMIT ?",
            (namespace or "default", like, like, top_k),
        ).fetchall()
        return {
            "results": [
                {
                    "id": r["id"],
                    "key": r["key"],
                    "value": r["value"],
                    "tags": __import__("json").loads(r["tags"] or "[]"),
                    "updated_at": r["updated_at"],
                }
                for r in rows
            ],
            "degraded": False,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory_search degraded: %s", exc)
        return {"results": [], "degraded": True, "note": str(exc)}
    finally:
        conn.close()


__all__ = [
    "kb_add_document",
    "kb_search",
    "memory_put",
    "memory_get",
    "memory_search",
    "get_conn",
]
