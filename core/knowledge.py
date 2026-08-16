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
import time
from datetime import datetime
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

# ---- LLM 扩写关键词缓存（优化③：同查询短 TTL 内不重复调 LLM） ----
_KEYWORD_CACHE_TTL = 3600  # 秒：同一自然语言查询 1h 内复用扩写结果
_keyword_cache: Dict[str, tuple] = {}  # {query: (expanded_tuple, expire_ts)}
_keyword_cache_lock = threading.Lock()


def _keyword_cache_get(query: str) -> Optional[List[str]]:
    """读扩写缓存（未命中/过期返回 None）。"""
    with _keyword_cache_lock:
        hit = _keyword_cache.get(query)
        if hit is None:
            return None
        expanded, expire = hit
        if time.time() > expire:
            _keyword_cache.pop(query, None)
            return None
        return list(expanded)


def _keyword_cache_put(query: str, expanded: List[str]) -> None:
    """写扩写缓存（限制容量防无限增长）。"""
    with _keyword_cache_lock:
        if len(_keyword_cache) >= 256:  # 简单容量上限
            # 清理已过期项；仍超限则整体清空（低频操作，可接受）
            now = time.time()
            expired = [k for k, (_, e) in _keyword_cache.items() if now > e]
            for k in expired:
                _keyword_cache.pop(k, None)
            if len(_keyword_cache) >= 256:
                _keyword_cache.clear()
        _keyword_cache[query] = (tuple(expanded), time.time() + _KEYWORD_CACHE_TTL)


def reset_keyword_cache() -> None:
    """测试/维护用：清空扩写缓存。"""
    with _keyword_cache_lock:
        _keyword_cache.clear()


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
        CREATE TABLE IF NOT EXISTS sessions_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            workspace TEXT NOT NULL DEFAULT 'shared',
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_summary_ws
            ON sessions_summary(workspace, updated_at);
        CREATE TABLE IF NOT EXISTS memory_user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            workspace TEXT NOT NULL DEFAULT 'shared',
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (workspace, key)
        );
        CREATE TABLE IF NOT EXISTS memory_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'deepddw',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_memory_notes_key ON memory_notes(key);
        CREATE TABLE IF NOT EXISTS memory_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_date TEXT NOT NULL,
            ts TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            content TEXT NOT NULL,
            auto INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_memory_logs_date ON memory_logs(log_date);
        CREATE TABLE IF NOT EXISTS memory_reflections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ref_date TEXT NOT NULL UNIQUE,
            content TEXT NOT NULL,
            style TEXT NOT NULL DEFAULT 'auto',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS memory_archive (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orig_table TEXT NOT NULL,
            orig_key TEXT,
            content TEXT NOT NULL,
            archived_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )
    conn.commit()
    # P1-1（multidevice）：workspace 列幂等迁移——已存在的旧表补列
    # （新表已含列；ALTER 对已有列抛 duplicate column，捕获忽略）。
    for table, col_sql in (
        ("memory_notes", "workspace TEXT NOT NULL DEFAULT 'shared'"),
        ("memory_logs", "workspace TEXT NOT NULL DEFAULT 'shared'"),
        ("memory_reflections", "workspace TEXT NOT NULL DEFAULT 'shared'"),
    ):
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_sql}")
        except sqlite3.OperationalError:
            pass  # 列已存在（幂等）
    # memory_user 特例：老表 UNIQUE(key) 无法支持 (workspace,key) 隔离——
    # 重建表并回填（幂等：老表存在且无 workspace 唯一约束时才做）。
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(memory_user)")]
        legacy = "workspace" not in cols
        if legacy:
            conn.execute("ALTER TABLE memory_user RENAME TO memory_user_legacy")
            conn.execute(
                "CREATE TABLE memory_user ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "key TEXT NOT NULL,"
                "value TEXT NOT NULL,"
                "workspace TEXT NOT NULL DEFAULT 'shared',"
                "updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
                "UNIQUE (workspace, key))"
            )
            conn.execute(
                "INSERT INTO memory_user (key, value, workspace, updated_at) "
                "SELECT key, value, 'shared', updated_at FROM memory_user_legacy"
            )
            conn.execute("DROP TABLE memory_user_legacy")
            conn.commit()
    except sqlite3.OperationalError:
        pass  # 已在迁移后状态（幂等）
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


def session_summary_save(
    session_id: str, title: str, summary: str, workspace: str = "shared",
) -> Dict[str, Any]:
    """保存会话摘要（P1-3 会话跨设备续接；同 session 覆盖）。

    摘要存 sessions_summary 表；手机端按 workspace 列出最近会话续问。
    """
    session_id = (session_id or "").strip()
    title = (title or session_id)[:200]
    summary = (summary or "").strip()[:2000]
    w = _ws(workspace)
    if not session_id:
        return {"ok": False, "note": "invalid session_id"}
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO sessions_summary (session_id, title, summary, workspace, "
            "updated_at) VALUES (?, ?, ?, ?, datetime('now')) "
            "ON CONFLICT(session_id) DO UPDATE SET title=excluded.title, "
            "summary=excluded.summary, workspace=excluded.workspace, "
            "updated_at=datetime('now')",
            (session_id, title, summary, w),
        )
        conn.commit()
        return {"ok": True, "session_id": session_id}
    except Exception as exc:  # noqa: BLE001
        logger.warning("session_summary_save degraded: %s", exc)
        return {"ok": False, "degraded": True, "note": str(exc)}
    finally:
        close_conn(conn)


def session_summary_list(
    limit: int = 5, workspace: str = "shared",
) -> Dict[str, Any]:
    """列出最近会话摘要（P1-3；按 workspace 过滤，默认 shared 向后兼容）。"""
    limit = max(1, min(int(limit or 5), 20))
    w = _ws(workspace)
    conn = get_conn()
    try:
        if w == "shared":
            rows = conn.execute(
                "SELECT session_id, title, summary, workspace, updated_at "
                "FROM sessions_summary "
                "WHERE (workspace = 'shared' OR workspace IS NULL) "
                "ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT session_id, title, summary, workspace, updated_at "
                "FROM sessions_summary WHERE workspace = ? "
                "ORDER BY updated_at DESC LIMIT ?",
                (w, limit),
            ).fetchall()
        return {"results": [dict(r) for r in rows], "degraded": False}
    except Exception as exc:  # noqa: BLE001
        logger.warning("session_summary_list degraded: %s", exc)
        return {"results": [], "degraded": True, "note": str(exc)}
    finally:
        close_conn(conn)


# ---------------------------------------------------------------------------
# 分层记忆（借鉴 dsh-auto-memory v0.1.23 的三层架构，SQLite 实现）
# ---------------------------------------------------------------------------

_MEMORY_CONTEXT_BUDGET = 2400  # 注入块预算字符（auto-memory injectBudgetChars）
_MEMORY_LOG_DAYS = 3  # 注入的最近日志天数
_MEMORY_USER_DAILY_BUDGET = 4000  # 用户级每日写入预算（auto-memory 4000）
_MEMORY_NOTE_DAILY_BUDGET = 3000  # 项目笔记每日预算（auto-memory 3000）


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")




def _ws(workspace: str) -> str:
    """workspace 归一化：None/空/shared → 'shared'；否则原样（已校验过合法性）。"""
    w = (workspace or "").strip()
    return w or "shared"


def _ws_where(workspace: str, col: str = "workspace") -> str:
    """按 workspace 过滤的 SQL 片段（shared 与旧数据一致）。"""
    w = _ws(workspace)
    if w == "shared":
        # 旧数据无 workspace 列默认 shared；显式 shared 与 NULL 都命中
        return f"({col} = 'shared' OR {col} IS NULL)"
    return f"{col} = ?"

def memory_user_put(key: str, value: str, workspace: str = "shared") -> Dict[str, Any]:
    """用户级规则/偏好（借鉴 auto-memory 用户级 MEMORY.md；upsert by key）。

    P1-1（multidevice）：workspace 隔离——非 shared 工作区按
    (workspace, key) 唯一；shared 与旧行为完全一致。
    """
    w = _ws(workspace)
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO memory_user (key, value, workspace, updated_at) "
            "VALUES (?, ?, ?, datetime('now')) "
            "ON CONFLICT(workspace, key) DO UPDATE SET value=excluded.value, "
            "workspace=excluded.workspace, updated_at=datetime('now')",
            (key, value, w),
        )
        conn.commit()
        return {"key": key, "workspace": w, "ok": True}
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory_user_put degraded: %s", exc)
        return {"ok": False, "degraded": True, "note": str(exc)}
    finally:
        close_conn(conn)


def memory_user_list(workspace: str = "shared") -> Dict[str, Any]:
    w = _ws(workspace)
    conn = get_conn()
    try:
        if w == "shared":
            rows = conn.execute(
                "SELECT key, value, updated_at FROM memory_user "
                "WHERE (workspace = 'shared' OR workspace IS NULL) "
                "ORDER BY updated_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT key, value, updated_at FROM memory_user "
                "WHERE workspace = ? ORDER BY updated_at DESC",
                (w,),
            ).fetchall()
        return {"results": [dict(r) for r in rows], "degraded": False}
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory_user_list degraded: %s", exc)
        return {"results": [], "degraded": True}
    finally:
        close_conn(conn)


def memory_note_put(
    key: str, value: str, source: str = "deepddw", workspace: str = "shared",
) -> Dict[str, Any]:
    """项目笔记/长期价值（借鉴 auto-memory 项目笔记 MEMORY.md；upsert by key）。

    P1-1（multidevice）：非 shared 工作区按 (workspace, key) 隔离。
    """
    w = _ws(workspace)
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO memory_notes (key, value, source, workspace, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now'), datetime('now')) "
            "ON CONFLICT DO UPDATE SET value=excluded.value, "
            "workspace=excluded.workspace, updated_at=datetime('now')",
            (key, value, source, w),
        )
        conn.commit()
        return {"key": key, "source": source, "workspace": w, "ok": True}
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory_note_put degraded: %s", exc)
        return {"ok": False, "degraded": True, "note": str(exc)}
    finally:
        close_conn(conn)


def memory_note_list(workspace: str = "shared") -> Dict[str, Any]:
    w = _ws(workspace)
    conn = get_conn()
    try:
        if w == "shared":
            rows = conn.execute(
                "SELECT key, value, source, updated_at FROM memory_notes "
                "WHERE (workspace = 'shared' OR workspace IS NULL) "
                "ORDER BY updated_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT key, value, source, updated_at FROM memory_notes "
                "WHERE workspace = ? ORDER BY updated_at DESC",
                (w,),
            ).fetchall()
        return {"results": [dict(r) for r in rows], "degraded": False}
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory_note_list degraded: %s", exc)
        return {"results": [], "degraded": True}
    finally:
        close_conn(conn)


def memory_log_append(
    content: str, auto: bool = False, workspace: str = "shared",
) -> Dict[str, Any]:
    """今日日志 append-only（借鉴 auto-memory 每日日志 YYYY-MM-DD.md）。

    P1-1：日志带 workspace 列（默认 shared 与旧行为一致）。
    """
    content = (content or "").strip()
    if not content:
        return {"ok": False, "note": "empty content"}
    w = _ws(workspace)
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO memory_logs (log_date, content, auto, workspace) "
            "VALUES (?, ?, ?, ?)",
            (_today(), content, 1 if auto else 0, w),
        )
        conn.commit()
        return {"id": cur.lastrowid, "log_date": _today(), "auto": auto,
                "workspace": w, "ok": True}
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory_log_append degraded: %s", exc)
        return {"ok": False, "degraded": True, "note": str(exc)}
    finally:
        close_conn(conn)


def memory_logs_recent(
    days: int = _MEMORY_LOG_DAYS, workspace: str = "shared",
) -> Dict[str, Any]:
    """最近 N 天日志（按日期倒序，供注入与检索）。

    P1-1：按 workspace 过滤（shared 含旧数据 NULL）。
    """
    w = _ws(workspace)
    conn = get_conn()
    try:
        if w == "shared":
            rows = conn.execute(
                "SELECT log_date, ts, content, auto FROM memory_logs "
                "WHERE log_date >= date('now', ?) "
                "AND (workspace = 'shared' OR workspace IS NULL) "
                "ORDER BY log_date DESC, id DESC",
                (f"-{int(days)} days",),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT log_date, ts, content, auto FROM memory_logs "
                "WHERE log_date >= date('now', ?) AND workspace = ? "
                "ORDER BY log_date DESC, id DESC",
                (f"-{int(days)} days", w),
            ).fetchall()
        return {"results": [dict(r) for r in rows], "degraded": False}
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory_logs_recent degraded: %s", exc)
        return {"results": [], "degraded": True}
    finally:
        close_conn(conn)


def memory_reflect_save(
    content: str, style: str = "auto", workspace: str = "shared",
) -> Dict[str, Any]:
    """每日反思（借鉴 auto-memory reflections/；同日期覆盖）。

    P1-1：反思带 workspace 列（非 shared 工作区各自独立）。
    """
    content = (content or "").strip()
    if not content:
        return {"ok": False, "note": "empty content"}
    w = _ws(workspace)
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO memory_reflections (ref_date, content, style, workspace, "
            "created_at) VALUES (?, ?, ?, ?, datetime('now')) "
            "ON CONFLICT(ref_date) DO UPDATE SET content=excluded.content, "
            "style=excluded.style, workspace=excluded.workspace",
            (_today(), content, style, w),
        )
        conn.commit()
        return {"ref_date": _today(), "workspace": w, "ok": True}
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory_reflect_save degraded: %s", exc)
        return {"ok": False, "degraded": True, "note": str(exc)}
    finally:
        close_conn(conn)


def memory_reflect_get(
    ref_date: str, workspace: str = "shared",
) -> Dict[str, Any]:
    w = _ws(workspace)
    conn = get_conn()
    try:
        if w == "shared":
            row = conn.execute(
                "SELECT ref_date, content, style FROM memory_reflections "
                "WHERE ref_date=? AND (workspace = 'shared' OR workspace IS NULL)",
                (ref_date,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT ref_date, content, style FROM memory_reflections "
                "WHERE ref_date=? AND workspace=?",
                (ref_date, w),
            ).fetchone()
        if row is None:
            return {"found": False}
        return {"found": True, **dict(row)}
    finally:
        close_conn(conn)


def _reflection_due() -> bool:
    """昨天有日志但今天/昨天无反思（借鉴 auto-memory 反思触发）。"""
    conn = get_conn()
    try:
        yesterday = conn.execute(
            "SELECT 1 FROM memory_logs WHERE log_date=date('now','-1 day') LIMIT 1"
        ).fetchone()
        if not yesterday:
            return False
        reflect = conn.execute(
            "SELECT 1 FROM memory_reflections WHERE ref_date IN "
            "(date('now'), date('now','-1 day')) LIMIT 1"
        ).fetchone()
        return reflect is None
    except Exception:  # noqa: BLE001
        return False
    finally:
        close_conn(conn)


async def memory_reflect_generate(style: str = "auto") -> Dict[str, Any]:
    """反思生成（LLM 增强版：auto-memory 每日反思的 AI 路径）。

    - 触发：昨天有日志且今/昨无反思（_reflection_due）；
    - LLM 基于最近 3 天日志生成反思正文并保存（风格可指定；结构化三段：
      进展/问题/明日注意；参考最近反思避免重复）；
    - LLM 不可用/超时/空输出 → due=True + generated=False（调用方提示
      "待反思"）；不满足触发 → due=False。全程不 500、不写空内容。
    """
    if not _reflection_due():
        return {"due": False, "ok": True, "generated": False}
    try:
        from core.llm_gateway.base import ChatMessage, ChatResponse
        from core.llm_gateway.gateway import chat as _gateway_chat

        logs = memory_logs_recent(days=3).get("results", [])
        if not logs:
            return {"due": True, "ok": True, "generated": False, "note": "no logs"}
        lines = "\n".join(
            f"- {r['log_date']}: {r['content'][:120]}" for r in logs[:12]
        )
        # 最近一条反思（避免连续两天内容雷同）
        prev = memory_reflect_get(
            __import__("datetime").date.today().strftime("%Y-%m-%d"),
        )
        prev_note = f"（昨日反思参考：{prev['content'][:100]}…）" if prev.get("found") else ""
        style_guide = {
            "auto": "简洁客观，突出事实与决策",
            "专业": "条理清晰，分点陈述，面向团队复盘",
            "生活化": "轻松自然，像写给自己的日记",
        }.get(style, "简洁客观，突出事实与决策")
        prompt = (
            f"请基于以下最近 3 天日志写一段每日反思（{style}风格，"
            f"{style_guide}）。\n"
            "要求：①按『进展 / 问题 / 明日注意』三段组织；②只输出正文，"
            "不要标题与序号前缀；③中文 80-200 字；④不与已有反思重复"
            f"{prev_note}。\n日志：\n{lines}"
        )
        resp: ChatResponse = await _gateway_chat(
            [ChatMessage(role="user", content=prompt)], rule=None
        )
        content = (resp.content or "").strip()
        if not content:
            return {"due": True, "ok": True, "generated": False, "note": "empty llm"}
        result = memory_reflect_save(content, style=style)
        return {
            "due": True, "ok": bool(result.get("ok", True)),
            "generated": True, "ref_date": result.get("ref_date"),
            "style": style,
        }
    except Exception as exc:  # noqa: BLE001
        logger.debug("memory reflect generate degraded: %s", exc)
        return {"due": True, "ok": True, "generated": False, "degraded": True}


def memory_context_build(
    budget: int = _MEMORY_CONTEXT_BUDGET, workspace: str = "shared",
) -> Dict[str, Any]:
    """组装 <memory_system> 注入块（借鉴 auto-memory SECTION_ORDER 注入）。

    内容：用户规则 + 项目笔记 + 最近反思 + 最近 N 天日志尾部；
    预算截断（保留头部规则 + 尾部日志，中间标注省略）。
    P1-1：按 workspace 组装（非 shared 只含该工作区记忆）。
    """
    parts: List[str] = []
    user = memory_user_list(workspace).get("results", [])
    if user:
        parts.append("## 用户规则/偏好")
        parts.extend(f"- {r['key']}: {r['value']}" for r in user)
    notes = memory_note_list(workspace).get("results", [])
    if notes:
        parts.append("## 项目笔记")
        parts.extend(f"- [{r['source']}] {r['key']}: {r['value']}" for r in notes[:10])
    logs = memory_logs_recent(_MEMORY_LOG_DAYS, workspace=workspace).get("results", [])
    if logs:
        parts.append("## 最近日志（尾部）")
        for r in logs[:15]:
            tag = "自动" if r.get("auto") else "手动"
            parts.append(f"- {r['log_date']} [{tag}] {r['content']}")
    body = "\n".join(parts)
    if len(body) > budget:
        # 预算截断：保留头部（规则/笔记）与尾部（日志），中间省略
        head = body[: budget // 2]
        tail = body[-budget // 2:]
        body = f"{head}\n…(记忆注入按预算截断，完整内容见检索)\n{tail}"
    if body:
        body = "<memory_system>\n" + body + "\n</memory_system>"
    return {
        "context": body,
        "chars": len(body),
        "budget": budget,
        "reflection_due": _reflection_due(),
        "degraded": False,
    }


def memory_budget_status() -> Dict[str, Any]:
    """当日写入预算统计（借鉴 auto-memory 每日预算；超限需 maintain 压缩）。"""
    conn = get_conn()
    try:
        user_row = conn.execute(
            "SELECT COALESCE(SUM(LENGTH(value)), 0) FROM memory_user "
            "WHERE updated_at >= date('now')"
        ).fetchone()
        user_chars = int(user_row[0]) if user_row else 0
        note_row = conn.execute(
            "SELECT COALESCE(SUM(LENGTH(value)), 0) FROM memory_notes "
            "WHERE updated_at >= date('now')"
        ).fetchone()
        note_chars = int(note_row[0]) if note_row else 0
        log_row = conn.execute(
            "SELECT COALESCE(SUM(LENGTH(content)), 0) FROM memory_logs "
            "WHERE log_date = date('now')"
        ).fetchone()
        log_chars = int(log_row[0]) if log_row else 0
        return {
            "user": {"chars": int(user_chars), "budget": _MEMORY_USER_DAILY_BUDGET},
            "notes": {"chars": int(note_chars), "budget": _MEMORY_NOTE_DAILY_BUDGET},
            "logs": {"chars": int(log_chars), "budget": 0},
            "over": int(user_chars) > _MEMORY_USER_DAILY_BUDGET
            or int(note_chars) > _MEMORY_NOTE_DAILY_BUDGET,
            "degraded": False,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory_budget_status degraded: %s", exc)
        return {"over": False, "degraded": True, "note": str(exc)}
    finally:
        close_conn(conn)


def memory_maintain() -> Dict[str, Any]:
    """预算超限压缩：AI 不可用时归档最旧笔记/规则（不丢数据，借鉴 auto-memory）。"""
    conn = get_conn()
    archived = 0
    try:
        status = memory_budget_status()
        if not status.get("over"):
            return {"archived": 0, "over": False, "note": "budget ok"}
        # 归档最旧的 notes 条目（超预算部分）
        rows = conn.execute(
            "SELECT id, key, value FROM memory_notes ORDER BY updated_at ASC LIMIT 5"
        ).fetchall()
        for r in rows:
            conn.execute(
                "INSERT INTO memory_archive (orig_table, orig_key, content) "
                "VALUES ('memory_notes', ?, ?)",
                (r["key"], r["value"]),
            )
            conn.execute("DELETE FROM memory_notes WHERE id=?", (r["id"],))
            archived += 1
        conn.commit()
        return {"archived": archived, "over": True, "note": "archived oldest notes"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory_maintain degraded: %s", exc)
        return {"archived": 0, "over": False, "degraded": True}
    finally:
        close_conn(conn)


def memory_consolidate(
    auto_consolidate_min_chars: int = 60,
) -> Dict[str, Any]:
    """自动沉淀（借鉴 auto-memory 每轮沉淀）。

    deepDDW 形态：供 chat 回复后调用（LLM 可用时由上层提炼；此处提供
    规则化沉淀：今日无日志时写一条占位，寒暄轮由调用方按长度跳过）。
    """
    # 本函数为规则/触发基座：具体沉淀内容由调用方（chat API / MCP
    # ddw.memory.consolidate）提供；此处只做去重与记录。
    conn = get_conn()
    try:
        today = _today()
        row = conn.execute(
            "SELECT COUNT(*) FROM memory_logs WHERE log_date=? AND auto=1",
            (today,),
        ).fetchone()
        count = int(row[0]) if row else 0
        return {
            "today_auto_count": int(count),
            "auto_consolidate_min_chars": auto_consolidate_min_chars,
            "ok": True,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory_consolidate degraded: %s", exc)
        return {"ok": False, "degraded": True}
    finally:
        close_conn(conn)


def memory_search_v2(
    query: str, top_k: int = 5, expand: bool = False, workspace: str = "shared",
) -> Dict[str, Any]:
    """分层检索（同步版；expand=True 时尝试 LLM 扩写，降级为原词）。

    async 调用方（API/MCP）请用 :func:`memory_search_v2_async` 获得
    真正的 LLM 扩写增强；本同步版 expand=True 在 LLM 不可达时同样
    降级为原词分词，语义一致。P1-1：按 workspace 过滤。
    """
    if expand:
        expanded = _llm_expand_keywords_sync(query)
        if expanded:
            return _search_v2_tokens(
                query, expanded, top_k, workspace=workspace, llm_expanded=expanded,
            )
    return _search_v2_tokens(query, None, top_k, workspace=workspace)


# 跨层排序权重（v0.3.0 记忆检索优化）：用户规则 > 项目笔记 > 反思 > 日志
_LAYER_WEIGHT = {"user": 4, "notes": 3, "reflection": 2, "logs": 1}


def _score_item(it: Dict[str, Any], tokens: List[str], now_ts: float) -> float:
    """轻量相关性评分：命中关键词数 × 层权重 + 新鲜度小量加分。

    命中数取 content+key 中出现的 token 数（含 LLM 扩写词）；
    新鲜度仅对 logs 层按日期近 3 天 +0.5（供排序微调，非硬约束）。
    """
    text = (str(it.get("content", "")) + " " + str(it.get("key", ""))).lower()
    hits = sum(1 for t in tokens if t and t.lower() in text)
    weight = _LAYER_WEIGHT.get(it.get("layer"), 1)
    freshness = 0.0
    if it.get("layer") == "logs" and it.get("date"):
        try:
            from datetime import datetime as _dt

            d = _dt.strptime(str(it["date"])[:10], "%Y-%m-%d")
            age_days = (now_ts - d.timestamp()) / 86400
            if age_days <= 3:
                freshness = 0.5
        except (ValueError, OSError):  # noqa: BLE001
            pass
    return float(hits) * weight + freshness


def _search_v2_tokens(
    query: str,
    tokens_override: Optional[List[str]],
    top_k: int,
    workspace: str = "shared",
    llm_expanded: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """分层检索核心：按关键词 OR 扫四层 + 来源标注（无 LLM 依赖）。

    v0.3.0 排序优化：按命中关键词数×层权重评分降序（user>notes>reflection>
    logs），同分按插入序稳定；logs 近 3 天小量加分。
    """
    w = _ws(workspace)
    from core.security.unicode_sanitizer import sanitize_unicode

    query = sanitize_unicode(query or "", max_length=200)
    tokens: List[str] = tokens_override or []
    if not tokens:
        tokens = [t for t in re.split(r"[\s,，、]+", query) if t][:8]
    if not tokens:
        return {
            "results": [], "degraded": False, "note": "empty query",
            "expanded": llm_expanded or [],
        }
    conn = get_conn()
    out: List[Dict[str, Any]] = []
    try:
        for tok in tokens:
            like = f"%{tok}%"
            for table, layer, key_col, val_col in (
                ("memory_user", "user", "key", "value"),
                ("memory_notes", "notes", "key", "value"),
                ("memory_logs", "logs", "log_date", "content"),
                ("memory_reflections", "reflection", "ref_date", "content"),
            ):
                try:
                    if w == "shared":
                        rows = conn.execute(
                            f"SELECT {key_col} AS k, {val_col} AS v FROM {table} "
                            f"WHERE ({val_col} LIKE ? OR {key_col} LIKE ?) "
                            f"AND (workspace = 'shared' OR workspace IS NULL) "
                            f"LIMIT 5",
                            (like, like),
                        ).fetchall()
                    else:
                        rows = conn.execute(
                            f"SELECT {key_col} AS k, {val_col} AS v FROM {table} "
                            f"WHERE ({val_col} LIKE ? OR {key_col} LIKE ?) "
                            f"AND workspace = ? LIMIT 5",
                            (like, like, w),
                        ).fetchall()
                except sqlite3.OperationalError:
                    continue
                for r in rows:
                    out.append({
                        "layer": layer,
                        "key": r["k"],
                        "content": (r["v"] or "")[:300],
                        "source": f"{layer}:{r['k']}",
                        # logs 层带日期供新鲜度评分；其余层 None
                        "date": r["k"] if layer == "logs" else None,
                    })
        # 去重（同一 layer+key）
        seen: set = set()
        dedup = []
        for it in out:
            sig = (it["layer"], it["key"])
            if sig in seen:
                continue
            seen.add(sig)
            dedup.append(it)
        # v0.3.0：跨层排序——评分降序（命中数×层权重 + 新鲜度），稳定排序
        now_ts = time.time()
        dedup.sort(key=lambda it: _score_item(it, tokens, now_ts), reverse=True)
        return {
            "results": dedup[: max(1, min(int(top_k), 20))],
            "degraded": False,
            "expanded": llm_expanded or [],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory_search_v2 degraded: %s", exc)
        return {"results": [], "degraded": True, "expanded": llm_expanded or []}
    finally:
        close_conn(conn)


def _llm_expand_keywords_sync(query: str) -> Optional[List[str]]:
    """同步壳：LLM 扩写（事件循环内自动跳过，返回 None → 降级原词）。"""
    try:
        import asyncio

        asyncio.get_running_loop()  # 已在事件循环中 → 不支持同步调用
        return None
    except RuntimeError:
        pass
    try:
        return asyncio.run(_llm_expand_keywords_async(query))
    except Exception as exc:  # noqa: BLE001
        logger.debug("memory llm expand sync degraded: %s", exc)
        return None


async def _llm_expand_keywords_async(query: str) -> Optional[List[str]]:
    """LLM 关键词扩写（auto-memory 智能检索：NL 查询 → 3-6 个检索关键词）。

    - 调用 deepDDW LLM 网关（浅 prompt）；超时/无 provider/非 JSON
      一律返回 None → 调用方降级为原词分词。
    - 严格只取 JSON 数组字符串；绝不编造来源（来源标注由检索层保证）。
    - 优化③：同查询 1h 内命中缓存，不重复调 LLM。
    """
    if not query or len(query) < 2:
        return None
    cached = _keyword_cache_get(query)
    if cached is not None:
        return cached
    try:
        import json as _json

        from core.llm_gateway.base import ChatMessage, ChatResponse
        from core.llm_gateway.gateway import chat as _gateway_chat

        prompt = (
            "你是记忆检索助手。把下面的用户查询扩写为 3-6 个中文检索关键词"
            "（覆盖同义词/相关实体/潜在记忆条目），只输出 JSON 字符串数组，"
            "不要任何解释或前后缀。\n查询："
            f"{query[:150]}"
        )
        resp: ChatResponse = await _gateway_chat(
            [ChatMessage(role="user", content=prompt)], rule=None
        )
        text = (resp.content or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\n?|```$", "", text).strip()
        m = re.search(r"\[.*?\]", text, re.S)
        if not m:
            return None
        items = _json.loads(m.group(0))
        if not isinstance(items, list):
            return None
        words = [str(i).strip() for i in items if str(i).strip()][:8]
        if words:
            _keyword_cache_put(query, words)
        return words or None
    except Exception as exc:  # noqa: BLE001
        logger.debug("memory llm expand degraded: %s", exc)
        return None


async def memory_search_v2_async(
    query: str, top_k: int = 5, expand: bool = True, workspace: str = "shared",
) -> Dict[str, Any]:
    """分层检索（async 增强版）：LLM 扩写关键词后 OR 扫描；失败降级原词。

    P1-1：按 workspace 过滤。
    """
    llm_expanded: Optional[List[str]] = None
    if expand:
        llm_expanded = await _llm_expand_keywords_async(query)
    return _search_v2_tokens(
        query, llm_expanded, top_k, workspace=workspace, llm_expanded=llm_expanded,
    )


async def memory_consolidate_llm(chat_text: str, user_id: int = 0) -> Dict[str, Any]:
    """LLM 提炼沉淀（auto-memory 每轮自动沉淀的 AI 路径）。

    用 LLM 从对话文本提炼 1-3 条可沉淀要点写入今日日志（auto=1）；
    LLM 不可用/超时 → 规则降级：首句摘要写一条（标注"规则沉淀"），
    寒暄（< 60 字符）跳过，不阻塞。
    """
    from core.security.unicode_sanitizer import sanitize_unicode

    text = sanitize_unicode(chat_text or "", max_length=20_000).strip()
    if not text:
        return {"ok": False, "note": "empty text", "degraded": False}
    if len(text) < 60:  # 寒暄/短轮跳过（auto-memory autoConsolidateMinChars）
        return {"ok": True, "skipped": "too_short", "wrote": 0}

    # LLM 路径
    try:
        import json as _json

        from core.llm_gateway.base import ChatMessage, ChatResponse
        from core.llm_gateway.gateway import chat as _gateway_chat

        prompt = (
            "从以下对话中提炼 1-3 条值得长期记住的要点（事实/决策/偏好/"
            "进展），每条一句话、中文、不超过 50 字；只输出 JSON 字符串数组，"
            "不要解释。若对话无价值内容输出 []。\n对话：\n"
            f"{text[:4000]}"
        )
        resp: ChatResponse = await _gateway_chat(
            [ChatMessage(role="user", content=prompt)], rule=None
        )
        raw = (resp.content or "").strip()
        m = re.search(r"\[.*?\]", raw, re.S)
        if m:
            items = _json.loads(m.group(0))
            if isinstance(items, list):
                points = [str(i).strip() for i in items if str(i).strip()][:3]
                if points:
                    written = 0
                    for p in points:
                        memory_log_append(p, auto=True)
                        written += 1
                    return {
                        "ok": True, "mode": "llm",
                        "wrote": written, "points": points,
                    }
                # LLM 明确判断无价值（返回 []）→ 不落日志（不触发规则降级）
                return {"ok": True, "mode": "llm", "wrote": 0,
                        "skipped": "no_value"}
    except Exception as exc:  # noqa: BLE001
        logger.debug("memory consolidate llm degraded: %s", exc)

    # 规则降级：仅 LLM 故障/超时/解析失败时——首句摘要
    first = re.split(r"[。！？\n]", text)[0].strip()
    summary = first[:80] or text[:80]
    memory_log_append(f"[规则沉淀] {summary}", auto=True)
    return {"ok": True, "mode": "rule", "wrote": 1, "summary": summary}


def migrate_memory_entries() -> Dict[str, Any]:
    """迁移旧 memory_entries → 新分层（不丢数据；旧表保留可回滚）。

    分类规则：tags 含 user/note/log/reflection 分别迁移；
    否则按 namespace（默认 user）；日志类按内容前缀 [自动沉淀] 判 auto。
    """
    import json as _json

    conn = get_conn()
    migrated = {"user": 0, "notes": 0, "logs": 0, "reflection": 0, "skipped": 0}
    try:
        rows = conn.execute(
            "SELECT id, namespace, key, value, tags FROM memory_entries"
        ).fetchall()
        for r in rows:
            tags = []
            try:
                tags = _json.loads(r["tags"] or "[]")
            except Exception:  # noqa: BLE001
                tags = []
            tags_l = [str(t).lower() for t in tags]
            ns = (r["namespace"] or "default").lower()
            value = r["value"] or ""
            if any("reflection" in t for t in tags_l) or "reflect" in ns:
                conn.execute(
                    "INSERT INTO memory_reflections (ref_date, content, style) "
                    "VALUES (date('now','-1 day'), ?, 'auto')",
                    (value,),
                )
                migrated["reflection"] += 1
            elif any("log" in t for t in tags_l) or "log" in ns:
                conn.execute(
                    "INSERT INTO memory_logs (log_date, content, auto) "
                    "VALUES (date('now'), ?, 1)",
                    (value,),
                )
                migrated["logs"] += 1
            elif any("note" in t for t in tags_l) or "note" in ns:
                conn.execute(
                    "INSERT INTO memory_notes (key, value, source) "
                    "VALUES (?, ?, 'migrated')",
                    (r["key"] or "note", value),
                )
                migrated["notes"] += 1
            else:
                conn.execute(
                    "INSERT INTO memory_user (key, value) VALUES (?, ?)",
                    (r["key"] or f"legacy-{r['id']}", value),
                )
                migrated["user"] += 1
        conn.commit()
        migrated["total"] = len(rows)
        return migrated
    except Exception as exc:  # noqa: BLE001
        logger.warning("migrate_memory_entries degraded: %s", exc)
        return {**migrated, "degraded": True, "note": str(exc)}
    finally:
        close_conn(conn)


__all__ = [
    "kb_add_document",
    "kb_search",
    "memory_put",
    "memory_get",
    "memory_search",
    "memory_user_put",
    "memory_user_list",
    "memory_note_put",
    "memory_note_list",
    "memory_log_append",
    "memory_logs_recent",
    "memory_reflect_save",
    "memory_reflect_get",
    "memory_reflect_generate",
    "memory_context_build",
    "memory_budget_status",
    "memory_maintain",
    "memory_consolidate",
    "memory_consolidate_llm",
    "memory_search_v2",
    "memory_search_v2_async",
    "migrate_memory_entries",
    "reset_keyword_cache",
    "session_doc_add",
    "session_docs_list",
    "session_summary_save",
    "session_summary_list",
    "get_conn",
]
