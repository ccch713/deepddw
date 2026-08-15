"""ddw_ai_readiness 评分与存储逻辑。"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "readiness.db"
_lock = threading.Lock()

GRADE1_A = 12   # 就绪度 A 阈值（含）
GRADE1_B = 7    # 就绪度 B 阈值（含）

VALID_SCENES = {"S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"}
VALID_CATS = {"D1", "D2", "D3", "D4"}


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT, name TEXT, phone TEXT,
            q1 INTEGER, q2 INTEGER, q3 INTEGER, q4 INTEGER, q5 INTEGER,
            q6 TEXT, q7 INTEGER,
            d TEXT, scenes TEXT,
            score1 INTEGER, grade1 TEXT, veto INTEGER,
            score2 INTEGER, grade_points INTEGER, grade TEXT,
            created_at TEXT
        )"""
    )
    return conn


def score_submission(data: dict) -> dict:
    """服务端评分（前端算分仅作即时反馈，入库以本函数为准）。"""
    def _int(v, lo, hi):
        try:
            v = int(v)
        except (TypeError, ValueError):
            return None
        return v if lo <= v <= hi else None

    q1 = _int(data.get("q1"), 0, 3)
    q2 = _int(data.get("q2"), 0, 3)
    q3 = _int(data.get("q3"), 0, 2)
    q4 = _int(data.get("q4"), 0, 3)
    q5 = _int(data.get("q5"), 0, 3)
    q7 = _int(data.get("q7"), 0, 3)
    missing = [x for x in (q1, q2, q3, q4, q5, q7) if x is None]
    if missing:
        raise ValueError("q1-q5/q7 必须为有效整数")

    # 第1段：就绪度
    score1 = q1 + q2 + q3 + q4 + q5 + q7
    veto = (q1 == 0 and q3 == 0)
    grade1 = "C" if veto else ("A" if score1 >= GRADE1_A else ("B" if score1 >= GRADE1_B else "C"))

    # 第2段：数据自评（缺失项按 0 处理）
    d = data.get("d") or {}
    score2 = 0
    for cat in VALID_CATS:
        c = d.get(cat) or {}
        for key in ("a", "b", "c"):
            v = _int(c.get(key), 0, 2)
            score2 += v if v is not None else 0

    # 商机分级：就绪度(1-3) + 痛点(1-3) + 预算决策(1-3)
    gp1 = {"A": 3, "B": 2, "C": 1}[grade1]
    gp2 = 3 if q4 >= 3 else (2 if q4 >= 2 else 1)
    gp3 = 3 if q7 >= 2 else (2 if q7 >= 1 else 1)
    grade_points = gp1 + gp2 + gp3
    grade = "A级" if grade_points >= 7 else ("B级" if grade_points >= 5 else "C级")

    return {
        "score1": score1, "grade1": grade1, "veto": veto,
        "score2": score2, "grade_points": grade_points, "grade": grade,
    }


def save_submission(payload: dict, scores: dict) -> int:
    scenes = [s for s in (payload.get("scenes") or []) if s in VALID_SCENES][:3]
    q6 = [s for s in (payload.get("q6") or [])][:10]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _lock:
        conn = _conn()
        cur = conn.execute(
            """INSERT INTO submissions
               (company,name,phone,q1,q2,q3,q4,q5,q6,q7,d,scenes,
                score1,grade1,veto,score2,grade_points,grade,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                (payload.get("company") or "")[:100],
                (payload.get("name") or "")[:50],
                (payload.get("phone") or "")[:50],
                payload.get("q1"), payload.get("q2"), payload.get("q3"),
                payload.get("q4"), payload.get("q5"),
                json.dumps(q6, ensure_ascii=False),
                payload.get("q7"),
                json.dumps(payload.get("d") or {}, ensure_ascii=False),
                json.dumps(scenes, ensure_ascii=False),
                scores["score1"], scores["grade1"], int(scores["veto"]),
                scores["score2"], scores["grade_points"], scores["grade"],
                now,
            ),
        )
        conn.commit()
        sid = cur.lastrowid
        conn.close()
    return sid


def get_submission(sid: int) -> dict | None:
    conn = _conn()
    row = conn.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
    conn.close()
    if not row:
        return None
    return _row_to_dict(row)


def list_submissions(limit: int = 50, offset: int = 0) -> list[dict]:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM submissions ORDER BY id DESC LIMIT ? OFFSET ?",
        (max(1, min(limit, 200)), max(0, offset)),
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_stats() -> dict:
    conn = _conn()
    row = conn.execute(
        """SELECT COUNT(*) total,
                  SUM(CASE WHEN grade='A级' THEN 1 ELSE 0 END) ga,
                  SUM(CASE WHEN grade='B级' THEN 1 ELSE 0 END) gb,
                  SUM(CASE WHEN grade='C级' THEN 1 ELSE 0 END) gc,
                  SUM(CASE WHEN grade1='A' THEN 1 ELSE 0 END) g1a,
                  SUM(CASE WHEN grade1='B' THEN 1 ELSE 0 END) g1b,
                  SUM(CASE WHEN grade1='C' THEN 1 ELSE 0 END) g1c
           FROM submissions"""
    ).fetchone()
    conn.close()
    return {
        "total": row["total"] or 0,
        "grade_a": row["ga"] or 0,
        "grade_b": row["gb"] or 0,
        "grade_c": row["gc"] or 0,
        "grade1_a": row["g1a"] or 0,
        "grade1_b": row["g1b"] or 0,
        "grade1_c": row["g1c"] or 0,
    }


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for k in ("q6", "d", "scenes"):
        try:
            d[k] = json.loads(d[k] or "[]" if k != "d" else d[k] or "{}")
        except (json.JSONDecodeError, TypeError):
            d[k] = [] if k != "d" else {}
    return d
