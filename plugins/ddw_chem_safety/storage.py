"""SQLite 存储层"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional


DB_PATH = Path(__file__).parent / "data" / "chem_safety.db"


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS hazard_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                area TEXT NOT NULL,
                hazard_type TEXT NOT NULL,
                description TEXT NOT NULL,
                image_urls TEXT DEFAULT '[]',
                reporter TEXT DEFAULT 'anonymous',
                status TEXT DEFAULT '待处理',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                resolved_at TEXT,
                resolution_note TEXT
            );

            CREATE TABLE IF NOT EXISTS training_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                options TEXT NOT NULL,
                correct_index INTEGER NOT NULL,
                explanation TEXT NOT NULL,
                category TEXT DEFAULT '通用',
                difficulty INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS regulations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                code TEXT NOT NULL UNIQUE,
                year INTEGER NOT NULL,
                category TEXT DEFAULT '法律',
                clauses TEXT DEFAULT '[]',
                applicable_scenarios TEXT DEFAULT '[]',
                created_at TEXT NOT NULL
            );
        """)
        conn.commit()
    finally:
        conn.close()


# ── 隐患上报 ──

def create_hazard(area: str, hazard_type: str, description: str,
                  image_urls: List[str], reporter: str) -> dict:
    now = datetime.now().isoformat()
    conn = _get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO hazard_reports (area, hazard_type, description, image_urls, reporter, status, created_at, updated_at) "  # noqa: E501
            "VALUES (?, ?, ?, ?, ?, '待处理', ?, ?)",
            (area, hazard_type, description, json.dumps(image_urls), reporter, now, now)
        )
        conn.commit()
        return get_hazard(cur.lastrowid)
    finally:
        conn.close()


def get_hazard(hazard_id: int) -> Optional[dict]:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM hazard_reports WHERE id = ?",
                           (hazard_id,)).fetchone()
        return _row_to_hazard(row) if row else None
    finally:
        conn.close()


def list_hazards(status: Optional[str] = None, page: int = 1, page_size: int = 20) -> dict:  # noqa: E501
    conn = _get_conn()
    try:
        where = "WHERE status = ?" if status else ""
        params = (status,) if status else ()

        total = conn.execute(
            f"SELECT COUNT(*) FROM hazard_reports {where}", params).fetchone()[0]

        offset = (page - 1) * page_size
        rows = conn.execute(
            f"SELECT * FROM hazard_reports {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + (page_size, offset)
        ).fetchall()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [_row_to_hazard(r) for r in rows]
        }
    finally:
        conn.close()


def update_hazard_status(hazard_id: int, status: str,
                         resolution_note: Optional[str] = None) -> Optional[dict]:
    now = datetime.now().isoformat()
    conn = _get_conn()
    try:
        resolved_at = now if status == "已闭环" else None
        conn.execute(
            "UPDATE hazard_reports SET status = ?, resolution_note = ?, updated_at = ?, resolved_at = ? WHERE id = ?",  # noqa: E501
            (status, resolution_note, now, resolved_at, hazard_id)
        )
        conn.commit()
        return get_hazard(hazard_id)
    finally:
        conn.close()


def count_hazards() -> int:
    conn = _get_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM hazard_reports").fetchone()[0]
    finally:
        conn.close()


def _row_to_hazard(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "area": row["area"],
        "hazard_type": row["hazard_type"],
        "description": row["description"],
        "image_urls": json.loads(row["image_urls"]),
        "reporter": row["reporter"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "resolved_at": row["resolved_at"],
        "resolution_note": row["resolution_note"],
    }


# ── 培训题库 ──

def insert_training_questions(questions: List[dict]):
    conn = _get_conn()
    try:
        existing = conn.execute("SELECT COUNT(*) FROM training_questions").fetchone()[0]
        if existing > 0:
            return
        for q in questions:
            conn.execute(
                "INSERT INTO training_questions (question, options, correct_index, explanation, category, difficulty) "  # noqa: E501
                "VALUES (?, ?, ?, ?, ?, ?)",
                (q["question"], json.dumps(q["options"]), q["correct_index"],
                 q["explanation"], q.get("category", "通用"), q.get("difficulty", 1))
            )
        conn.commit()
    finally:
        conn.close()


def get_random_question() -> Optional[dict]:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM training_questions ORDER BY RANDOM() LIMIT 1").fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "question": row["question"],
            "options": json.loads(row["options"]),
            "correct_index": row["correct_index"],
            "explanation": row["explanation"],
            "category": row["category"],
            "difficulty": row["difficulty"],
        }
    finally:
        conn.close()


def get_question_by_id(question_id: int) -> Optional[dict]:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM training_questions WHERE id = ?", (question_id,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "question": row["question"],
            "options": json.loads(row["options"]),
            "correct_index": row["correct_index"],
            "explanation": row["explanation"],
            "category": row["category"],
            "difficulty": row["difficulty"],
        }
    finally:
        conn.close()


def count_questions() -> int:
    conn = _get_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM training_questions").fetchone()[0]
    finally:
        conn.close()


# ── 法规语料 ──

def _row_to_regulation(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "code": row["code"],
        "year": row["year"],
        "category": row["category"],
        "clauses": json.loads(row["clauses"]),
        "applicable_scenarios": json.loads(row["applicable_scenarios"]),
        "created_at": row["created_at"],
    }


def seed_regulations(regulations: List[dict]) -> dict:
    """批量写入法规语料，code 唯一约束保证幂等，重复的跳过。"""
    now = datetime.now().isoformat()
    inserted = 0
    skipped = 0
    conn = _get_conn()
    try:
        for reg in regulations:
            try:
                conn.execute(
                    "INSERT INTO regulations (name, code, year, category, clauses, applicable_scenarios, created_at) "  # noqa: E501
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        reg["name"],
                        reg["code"],
                        reg["year"],
                        reg.get("category", "法律"),
                        json.dumps(reg.get("clauses", []), ensure_ascii=False),
                        json.dumps(reg.get("applicable_scenarios", []),
                                   ensure_ascii=False),
                        now,
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                skipped += 1
        conn.commit()
    finally:
        conn.close()
    return {"inserted": inserted, "skipped": skipped, "total": len(regulations)}


def list_regulations() -> List[dict]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM regulations ORDER BY year DESC, id").fetchall()
        return [_row_to_regulation(r) for r in rows]
    finally:
        conn.close()


def get_regulation(reg_id: int) -> Optional[dict]:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM regulations WHERE id = ?",
                           (reg_id,)).fetchone()
        return _row_to_regulation(row) if row else None
    finally:
        conn.close()


def search_regulations(keyword: str) -> List[dict]:
    """在法规名称、编号、条款摘要、适用场景中搜索关键词。"""
    conn = _get_conn()
    try:
        pattern = f"%{keyword}%"
        rows = conn.execute(
            "SELECT * FROM regulations "
            "WHERE name LIKE ? OR code LIKE ? OR clauses LIKE ? OR applicable_scenarios LIKE ? "  # noqa: E501
            "ORDER BY year DESC, id",
            (pattern, pattern, pattern, pattern),
        ).fetchall()
        return [_row_to_regulation(r) for r in rows]
    finally:
        conn.close()


def count_regulations() -> int:
    conn = _get_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM regulations").fetchone()[0]
    finally:
        conn.close()
