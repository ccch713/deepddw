"""deepDDW 个人级知识库 + 轻量记忆服务（开源白名单组件）。

- 知识库：``kb_documents`` 表（title/content），**向量 + 关键词混合检索**：
  入库时生成 hash-trick 512 维 embedding 写 LanceDB（Apache-2.0，可选增强，
  ``LANCEDB_PATH`` 存在时启用）；检索 = 向量 cosine 与 FTS5/LIKE 关键词
  RRF 融合；LanceDB 不可用时自动降级纯关键词，不阻塞主流程。
- 记忆：``memory_entries`` 表，键值/列表式长期记忆（deepDDW v0.1 内置实现；
  部署可另接 agentmemory MCP 服务作为外部记忆后端）。

设计原则：
- 断网/存储故障不阻塞对话主流程：所有查询失败都返回空结果 + ``degraded=True``。
- 本模块为 core 服务层：MCP 工具（ddw.kb.search / ddw.memory.*）与 REST API 共用。
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import get_settings

logger = logging.getLogger(__name__)

_DB_PATH_DEFAULT = "./data/ddw_main.db"

# FTS5 是否可用的运行时探测缓存
_fts_available: Optional[bool] = None

_FTS_CREATE = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING "
    "fts5(title, content, content='kb_documents', content_rowid='id')"
)

# ---- LanceDB 向量检索（可选增强；不可用自动降级） ----
_VECTOR_DIM = 512
_LANCE_DIR_DEFAULT = "./data/kb_vectors.lance"
_VECTOR_TABLE = "kb_vectors"
_RRF_K = 60  # RRF 融合常数：score = Σ 1/(k + rank)

# hash-trick 词频 embedding 的运行时探测缓存
_lance_available_cache: Optional[bool] = None


# ---------------------------------------------------------------------------
# 连接与建表
# ---------------------------------------------------------------------------


def _db_path() -> Path:
    settings = get_settings()
    cfg = settings.databases.get("main", {})
    if cfg.get("engine") == "sqlite":
        return Path(cfg.get("path", _DB_PATH_DEFAULT)).resolve()
    return Path(_DB_PATH_DEFAULT).resolve()


# P1-15：模块级单连接 + 全局锁复用（按库路径自动重建；线程安全；
# 单连接串行化 kb/记忆操作，天然避免 SQLITE_BUSY；测试 reset 全局可见）
_shared_conn = None
_shared_path: Optional[str] = None
_conn_lock = threading.Lock()


def get_conn() -> sqlite3.Connection:
    """同步 SQLite 连接（模块级单连接复用 + 锁；避免每次建连的 fd 与 IO 开销）。"""
    global _shared_conn, _shared_path
    path = _db_path()
    with _conn_lock:
        if _shared_conn is None or _shared_path != str(path):
            if _shared_conn is not None:
                try:
                    _shared_conn.close()
                except sqlite3.Error:  # noqa: BLE001
                    pass
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
        str(path), timeout=10, check_same_thread=False
    )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            _ensure_schema(conn)
            _shared_conn = conn
            _shared_path = str(path)
        return _shared_conn


def close_conn(conn: sqlite3.Connection) -> None:
    """归还连接（单连接复用——no-op，连接由模块持有/路径切换时重建）。"""


def reset_conn_pool() -> None:
    """关闭并清空共享连接（测试隔离 / 关闭时调用；全局可见）。"""
    global _shared_conn, _shared_path
    with _conn_lock:
        if _shared_conn is not None:
            try:
                _shared_conn.close()
            except sqlite3.Error:  # noqa: BLE001
                pass
        _shared_conn = None
        _shared_path = None


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
        CREATE INDEX IF NOT EXISTS idx_memory_namespace
            ON memory_entries(namespace, key);
        CREATE TABLE IF NOT EXISTS session_docs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            doc_id INTEGER NOT NULL,
            kind TEXT NOT NULL DEFAULT 'chat',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_session_docs_sid
            ON session_docs(session_id);
        """
    )
    conn.commit()


def _tokenize(text: str) -> List[str]:
    """中文/英文/数字 token 化（复用 FTS 清洗规则）。"""
    raw = re.findall(r"[0-9A-Za-z_\-]+|[\u4e00-\u9fff]", (text or "").lower())
    return [t for t in raw if t]


def _embed(text: str, dim: int = _VECTOR_DIM) -> List[float]:
    """hash-trick + 词频加权（log1p）的零依赖 embedding，L2 归一化。

    确定性：同一文本每次产出相同向量（同词同桶）。512 维对个人级知识库
    足够表达词频分布；语义相似文档共享高频词桶，cosine 可排序。
    """
    vec = [0.0] * dim
    counts: Dict[str, int] = {}
    for tok in _tokenize(text):
        counts[tok] = counts.get(tok, 0) + 1
    for tok, count in counts.items():
        bucket = int(hashlib.sha256(tok.encode("utf-8")).hexdigest(), 16) % dim
        vec[bucket] += math.log1p(count)
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def _lance_dir() -> Path:
    """LanceDB 目录：env ``LANCEDB_PATH`` > 知识库主库同目录（随 _db_path）。"""
    override = __import__("os").environ.get("LANCEDB_PATH")
    if override:
        return Path(override).resolve()
    return _db_path().resolve().parent / "kb_vectors.lance"


def _lance_available() -> bool:
    """LanceDB 可用性探测（import 成功 + 目录可写）。"""
    global _lance_available_cache
    if _lance_available_cache is None:
        try:
            import lancedb  # noqa: F401

            _lance_dir().mkdir(parents=True, exist_ok=True)
            _lance_available_cache = True
        except Exception as exc:  # noqa: BLE001
            logger.debug("lancedb unavailable: %s", exc)
            _lance_available_cache = False
    return _lance_available_cache


def _vector_add(doc_id: int, title: str, content: str) -> None:
    """写入/更新向量（幂等 upsert by doc_id）；失败仅告警。"""
    if not _lance_available():
        return
    try:
        import lancedb

        db = lancedb.connect(str(_lance_dir()))
        table = _get_or_create_vector_table(db)
        vector = _embed(f"{title}\n{content}")
        existing = None
        try:
            existing = table.search(vector).where(
                f"doc_id = {doc_id}", prefilter=True).limit(1).to_list()
        except Exception:  # noqa: BLE001  # 空表/无该行
            existing = None
        data = [{
            "doc_id": doc_id,
            "title": title,
            "content": content,
            "vector": vector,
        }]
        if existing:
            table.delete(f"doc_id = {doc_id}")
        table.add(data)
    except Exception as exc:  # noqa: BLE001  # 向量故障不阻塞入库
        logger.warning("kb vector add failed (degraded): %s", exc)


def _get_or_create_vector_table(db):
    if _VECTOR_TABLE in db.table_names():
        return db.open_table(_VECTOR_TABLE)
    return db.create_table(
        _VECTOR_TABLE,
        data=[{
            "doc_id": 0,
            "title": "",
            "content": "",
            "vector": [0.0] * _VECTOR_DIM,
        }],
    )


def _vector_search(query: str, top_k: int) -> List[Dict[str, Any]]:
    """LanceDB cosine 检索；失败返回空列表（上层降级）。"""
    if not _lance_available():
        return []
    try:
        import lancedb

        db = lancedb.connect(str(_lance_dir()))
        if _VECTOR_TABLE not in db.table_names():
            return []
        table = db.open_table(_VECTOR_TABLE)
        q = _embed(query)
        rows = table.search(q).limit(top_k).to_list()
        out = []
        for r in rows:
            if r.get("doc_id"):
                out.append({
                    "doc_id": r["doc_id"],
                    "title": r.get("title", ""),
                    "content": r.get("content", ""),
                    "score": float(r.get("_distance", 1.0)),
                    "_src": "vector",
                })
        return out
    except Exception as exc:  # noqa: BLE001
        logger.debug("kb vector search failed (degraded): %s", exc)
        return []


def _rrf_fuse(lists: List[List[Dict[str, Any]]], top_k: int) -> List[Dict[str, Any]]:
    """RRF 融合多个检索结果（按 doc_id 合并，score = Σ 1/(k+rank)）。"""
    merged: Dict[int, Dict[str, Any]] = {}
    for ranked in lists:
        for rank, item in enumerate(ranked):
            did = int(item.get("doc_id") or 0)
            if not did:
                continue
            entry = merged.setdefault(did, {
                "doc_id": did,
                "title": item.get("title", ""),
                "content": item.get("content", ""),
                "score": 0.0,
                "sources": [],
            })
            entry["score"] += 1.0 / (_RRF_K + rank + 1)
            entry["sources"].append(item.get("_src", "keyword"))
    ranked = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
    return ranked[:top_k]


def _fts_supported(conn: sqlite3.Connection) -> bool:
    global _fts_available
    if _fts_available is None:
        try:
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS _kb_fts_test USING fts5(x)"
            )
            _fts_available = True
        except sqlite3.OperationalError:
            _fts_available = False
    return _fts_available


# ---------------------------------------------------------------------------
# 知识库
# ---------------------------------------------------------------------------


def kb_add_document(
    title: str, content: str, category: str = "public"
) -> Dict[str, Any]:
    """新增知识文档。"""
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO kb_documents (title, content, category) "
            "VALUES (?, ?, ?)",
            (title, content, category),
        )
        conn.commit()
        doc_id = cur.lastrowid
        if _fts_supported(conn):
            try:
                conn.execute(_FTS_CREATE)
                conn.execute(
                    "INSERT INTO kb_fts (rowid, title, content) VALUES (?, ?, ?)",
                    (doc_id, title, content),
                )
                conn.commit()
            except sqlite3.OperationalError as exc:  # noqa: BLE001
                logger.warning("kb fts index failed, fallback to LIKE: %s", exc)
        _vector_add(doc_id, title, content)  # 向量增强（失败仅告警，不阻塞）
        return {"id": doc_id, "title": title, "category": category}
    finally:
        close_conn(conn)


def kb_search(query: str, top_k: int = 5) -> Dict[str, Any]:
    """知识库关键词检索（FTS5 优先，退化 LIKE）。

    失败返回空结果 + degraded 标记（不阻塞主流程）。
    """
    top_k = max(1, min(int(top_k or 5), 20))
    query = (query or "").strip()
    if not query:
        return {"results": [], "degraded": False, "note": "empty query"}
    try:
        conn = get_conn()
        keyword: List[Dict[str, Any]] = []
        try:
            if _fts_supported(conn):
                try:
                    conn.execute(_FTS_CREATE)
                    rows = conn.execute(
                        "SELECT d.id, d.title, d.content, d.category, "
                        "bm25(kb_fts) AS score "
                        "FROM kb_fts JOIN kb_documents d ON d.id = kb_fts.rowid "
                        "WHERE kb_fts MATCH ? ORDER BY score LIMIT ?",
                        (_fts_query(query), top_k * 2),
                    ).fetchall()
                    keyword = [_kb_row(r, src="keyword") for r in rows]
                except sqlite3.OperationalError as exc:  # noqa: BLE001
                    logger.debug("kb fts query failed, fallback to LIKE: %s", exc)
            if not keyword:
                # LIKE 兜底：按 title/content 命中粗排序
                like = f"%{query}%"
                rows = conn.execute(
                    "SELECT id, title, content, category, 0 AS score "
                    "FROM kb_documents WHERE title LIKE ? OR content LIKE ? "
                    "ORDER BY id DESC LIMIT ?",
                    (like, like, top_k * 2),
                ).fetchall()
                keyword = [_kb_row(r, src="keyword") for r in rows]
        finally:
            close_conn(conn)

        # 向量检索（LanceDB 可用时）→ RRF 融合
        vector_hits = _vector_search(query, top_k * 2)
        if vector_hits:
            fused = _rrf_fuse([vector_hits, keyword], top_k)
            return {
                "results": [_fused_row(x) for x in fused],
                "degraded": False,
                "mode": "hybrid",
                "sources": _fused_sources(fused),
            }
        return {
            "results": [_fused_row(x) for x in keyword[:top_k]],
            "degraded": False,
            "mode": "keyword",
        }
    except Exception as exc:  # noqa: BLE001  # 存储故障不阻塞主流程
        logger.warning("kb_search degraded: %s", exc)
        return {"results": [], "degraded": True, "note": str(exc)}


def _fused_row(item: Dict[str, Any]) -> Dict[str, Any]:
    """融合条目 → 统一输出结构。"""
    content = item.get("content") or ""
    excerpt = content[:200] + ("…" if len(content) > 200 else "")
    return {
        "id": int(item.get("doc_id") or 0),
        "title": item.get("title", ""),
        "excerpt": excerpt,
        "category": item.get("category", "public"),
        "score": round(float(item.get("score") or 0.0), 4),
        "sources": item.get("sources", []),
    }


def _fused_sources(fused: List[Dict[str, Any]]) -> List[str]:
    seen: List[str] = []
    for x in fused:
        for src in x.get("sources", []):
            if src not in seen:
                seen.append(src)
    return seen


# P1-12：FTS5 MATCH 输入严格清洗——只允许字母/数字/中文/下划线，
# 首尾 strip 掉 `-_`（防构造 FTS 操作符），并做 NFKC 归一化（防变体/零宽注入）
_FTS_SAFE_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff_]")


def _fts_query(query: str) -> str:
    """把用户查询转成 FTS5 安全 MATCH 表达式（NFKC 归一 + 严格清洗，按词 AND）。"""
    import unicodedata

    norm = unicodedata.normalize("NFKC", query or "")
    tokens = [t for t in re.split(r"\s+", norm) if t]
    cleaned = []
    for t in tokens:
        c = _FTS_SAFE_RE.sub("", t).strip("-_")
        if c:
            cleaned.append(c)
    if not cleaned:
        return '""'  # 空查询：不匹配任何内容（比裸拼原文安全）
    return " AND ".join(f'"{c}"' for c in cleaned[:8])


def _kb_row(row: sqlite3.Row, src: str = "keyword") -> Dict[str, Any]:
    content = row["content"] or ""
    excerpt = content[:200] + ("…" if len(content) > 200 else "")
    return {
        "id": row["id"],
        "title": row["title"],
        "content": content,
        "excerpt": excerpt,
        "category": row["category"],
        "score": float(row["score"]) if "score" in row.keys() else 0.0,
        "_src": src,
    }


# ---------------------------------------------------------------------------
# 记忆（轻量 SQLite 实现；外部 agentmemory MCP 可选接入）
# ---------------------------------------------------------------------------


def memory_put(
    namespace: str, key: str, value: str, tags: Optional[List[str]] = None
) -> Dict[str, Any]:
    """写入一条记忆（同 namespace+key 覆盖）。"""
    ns = namespace or "default"
    tags_json = __import__("json").dumps(tags or [], ensure_ascii=False)
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT id FROM memory_entries WHERE namespace=? AND key=?",
            (ns, key),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE memory_entries SET value=?, tags=?, "
                "updated_at=datetime('now') WHERE id=?",
                (value, tags_json, existing["id"]),
            )
            mem_id = existing["id"]
        else:
            cur = conn.execute(
                "INSERT INTO memory_entries "
                "(namespace, key, value, tags) VALUES (?, ?, ?, ?)",
                (ns, key, value, tags_json),
            )
            mem_id = cur.lastrowid
        conn.commit()
        return {"id": mem_id, "namespace": ns, "key": key, "ok": True}
    finally:
        close_conn(conn)


def memory_get(namespace: str, key: str) -> Dict[str, Any]:
    """读取单条记忆；缺失返回 found=False（不抛错）。"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM memory_entries WHERE namespace=? AND key=?",
            (namespace or "default", key),
        ).fetchone()
        if row is None:
            return {"found": False, "value": None}
        return {
            "found": True,
            "value": row["value"],
            "tags": __import__("json").loads(row["tags"] or "[]"),
        }
    finally:
        close_conn(conn)


def memory_search(namespace: str, query: str, top_k: int = 5) -> Dict[str, Any]:
    """按内容关键词检索记忆（LIKE 匹配 value/tags）。"""
    top_k = max(1, min(int(top_k or 5), 20))
    like = f"%{query}%"
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM memory_entries WHERE namespace=? "
            "AND (value LIKE ? OR tags LIKE ?) "
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
        close_conn(conn)


def session_doc_add(
    session_id: str, title: str, content: str, kind: str = "chat"
) -> Dict[str, Any]:
    """会话→文档闭环：建知识库文档并关联到会话（对话产出文档入库）。

    失败返回 degraded 标记（不阻塞调用方）。
    """
    try:
        doc = kb_add_document(title, content, category="session")
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO session_docs (session_id, doc_id, kind) "
                "VALUES (?, ?, ?)",
                (session_id, int(doc["id"]), kind),
            )
            conn.commit()
        finally:
            close_conn(conn)
        return {"id": doc["id"], "title": title, "session_id": session_id, "ok": True}
    except Exception as exc:  # noqa: BLE001
        logger.warning("session_doc_add degraded: %s", exc)
        return {"ok": False, "degraded": True, "note": str(exc)}


def session_docs_list(session_id: str, limit: int = 50) -> Dict[str, Any]:
    """按会话列出产出文档（join kb_documents）；失败返回空 + degraded。"""
    limit = max(1, min(int(limit or 50), 200))
    try:
        conn = get_conn()
        try:
            rows = conn.execute(
                "SELECT d.id, d.title, d.content, d.category, "
                "sd.kind, sd.created_at "
                "FROM session_docs sd JOIN kb_documents d ON d.id = sd.doc_id "
                "WHERE sd.session_id = ? ORDER BY sd.id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        finally:
            close_conn(conn)
        return {
            "results": [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "kind": r["kind"],
                    "category": r["category"],
                    "excerpt": (r["content"] or "")[:200],
                    "created_at": r["created_at"],
                }
                for r in rows
            ],
            "degraded": False,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("session_docs_list degraded: %s", exc)
        return {"results": [], "degraded": True, "note": str(exc)}


__all__ = [
    "kb_add_document",
    "kb_search",
    "memory_put",
    "memory_get",
    "memory_search",
    "session_doc_add",
    "session_docs_list",
    "get_conn",
]
