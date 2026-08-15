"""DDW LLM 用量中枢 — SQLite 存储层。

设计要点：
    * 独立数据库文件（默认 plugins/ddw_llm_usage/data/llm_usage.db），
      不耦合底座主 DB，部署/迁移/清空都方便；
    * 同步 sqlite3 + 内部锁（check_same_thread=False），FastAPI 通过
      线程池跑 sync 路由，避免额外异步驱动依赖；
    * 幂等写入：usage_records.id 是主键，重复插入直接忽略；
    * 价格表持久化：model_prices 表，存的是「运行时覆盖」值，
      与代码里的 DEFAULT_PRICES 合并读取。
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from .models import (
    DEFAULT_PRICES,
    ModelPrice,
    UsageRecord,
    compute_cost_cents,
    resolve_price,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_records (
    id                TEXT PRIMARY KEY,
    ts                TEXT NOT NULL,             -- ISO-8601 UTC
    plugin            TEXT NOT NULL,
    user              TEXT NOT NULL,
    model             TEXT NOT NULL,
    provider          TEXT NOT NULL,
    input_tokens      INTEGER NOT NULL,
    output_tokens     INTEGER NOT NULL,
    cache_hit_tokens  INTEGER NOT NULL DEFAULT 0,
    cost_cents        INTEGER NOT NULL,
    session_id        TEXT,
    pricing_defaulted INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_usage_ts        ON usage_records(ts);
CREATE INDEX IF NOT EXISTS idx_usage_model     ON usage_records(model);
CREATE INDEX IF NOT EXISTS idx_usage_plugin    ON usage_records(plugin);
CREATE INDEX IF NOT EXISTS idx_usage_user      ON usage_records(user);

CREATE TABLE IF NOT EXISTS model_prices (
    model            TEXT PRIMARY KEY,
    input_price      REAL NOT NULL,
    output_price     REAL NOT NULL,
    cache_hit_price  REAL NOT NULL DEFAULT 0,
    provider         TEXT
);
"""


# ---------------------------------------------------------------------------
# Storage 类
# ---------------------------------------------------------------------------


class UsageStorage:
    """SQLite 存储层。线程安全（自带锁）。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()
        # 价格表自启动时为一张「干净状态表」——运行期被 PUT 改动的值才落盘
        logger.debug("ddw_llm_usage storage ready at %s", self.db_path)

    # ---- 基础 ----

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._lock, self._conn() as conn:
            conn.executescript(_SCHEMA)

    # ---- 写入 ----

    def insert_record(self, rec: UsageRecord) -> bool:
        """插入一条记录；返回 True 表示新增，False 表示幂等命中（已存在忽略）。"""
        with self._lock, self._conn() as conn:
            cur = conn.execute("SELECT 1 FROM usage_records WHERE id = ?", (rec.id,))
            if cur.fetchone() is not None:
                return False
            conn.execute(
                """
                INSERT INTO usage_records (
                    id, ts, plugin, "user", model, provider,
                    input_tokens, output_tokens, cache_hit_tokens,
                    cost_cents, session_id, pricing_defaulted
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec.id,
                    rec.ts.isoformat(),
                    rec.plugin,
                    rec.user,
                    rec.model,
                    rec.provider,
                    rec.input_tokens,
                    rec.output_tokens,
                    rec.cache_hit_tokens,
                    rec.cost_cents,
                    rec.session_id,
                    1 if rec.pricing_defaulted else 0,
                ),
            )
            return True

    def get_record(self, rec_id: str) -> Optional[UsageRecord]:
        """按 id 查询单条记录（用于幂等语义——返回的是数据库真实值）。"""
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM usage_records WHERE id = ?", (rec_id,)).fetchone()
        if row is None:
            return None
        return UsageRecord(
            id=row["id"],
            ts=datetime.fromisoformat(row["ts"]),
            plugin=row["plugin"],
            user=row["user"],
            model=row["model"],
            provider=row["provider"],
            input_tokens=int(row["input_tokens"]),
            output_tokens=int(row["output_tokens"]),
            cache_hit_tokens=int(row["cache_hit_tokens"]),
            cost_cents=int(row["cost_cents"]),
            session_id=row["session_id"],
            pricing_defaulted=bool(row["pricing_defaulted"]),
        )

    # ---- 价格表 ----

    def list_prices(self) -> dict[str, ModelPrice]:
        """返回「代码默认 + 运行时覆盖」合并后的单价表。"""
        merged: dict[str, ModelPrice] = {k: v for k, v in DEFAULT_PRICES.items()}
        with self._lock, self._conn() as conn:
            for row in conn.execute(
                "SELECT model, input_price, output_price, cache_hit_price, provider FROM model_prices"  # noqa: E501
            ).fetchall():
                merged[row["model"]] = ModelPrice(
                    model=row["model"],
                    input_price=row["input_price"],
                    output_price=row["output_price"],
                    cache_hit_price=row["cache_hit_price"],
                    provider=row["provider"],
                )
        return merged

    def upsert_price(self, price: ModelPrice) -> None:
        """写入/更新一条单价；返回受影响行数（调试用）。"""
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                INSERT INTO model_prices (model, input_price, output_price,
                cache_hit_price, provider)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(model) DO UPDATE SET
                    input_price=excluded.input_price,
                    output_price=excluded.output_price,
                    cache_hit_price=excluded.cache_hit_price,
                    provider=excluded.provider
                """,
                (
                    price.model,
                    price.input_price,
                    price.output_price,
                    price.cache_hit_price,
                    price.provider,
                ),
            )

    def delete_price(self, model: str) -> int:
        """删除一条覆盖价（回到默认价）；返回受影响行数。"""
        with self._lock, self._conn() as conn:
            cur = conn.execute("DELETE FROM model_prices WHERE model = ?", (model,))
            return cur.rowcount

    # ---- 统计 ----

    @staticmethod
    def _days_param(days: int) -> str:
        """生成 SQLite 的 datetime('now', ?) 参数（负偏移）。"""
        return f"-{int(days)} days"

    def _summary(
        self,
        days: int,
    ) -> tuple[int, int, int, int, int]:
        """返回 (calls, input_tokens, output_tokens, cache_hit_tokens, total_cents)。"""
        with self._lock, self._conn() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*)                                          AS calls,
                    COALESCE(SUM(input_tokens), 0)                   AS input_tokens,
                    COALESCE(SUM(output_tokens), 0)                  AS output_tokens,
                    COALESCE(SUM(cache_hit_tokens), 0)               AS
                    cache_hit_tokens,
                    COALESCE(SUM(cost_cents), 0)                     AS total_cents
                FROM usage_records
                WHERE ts >= datetime('now', ?)
                """,
                (self._days_param(days),),
            ).fetchone()
            return (
                int(row["calls"]),
                int(row["input_tokens"]),
                int(row["output_tokens"]),
                int(row["cache_hit_tokens"]),
                int(row["total_cents"]),
            )

    def _grouped(
        self,
        group_by: str,
        days: int,
    ) -> list[dict[str, Any]]:
        """按某个字段分组聚合（model / plugin / user）。"""
        if group_by not in {"model", "plugin", "user"}:
            raise ValueError(f"unsupported group_by: {group_by}")
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    {group_by}                                        AS key,
                    COUNT(*)                                          AS calls,
                    COALESCE(SUM(input_tokens), 0)                   AS input_tokens,
                    COALESCE(SUM(output_tokens), 0)                  AS output_tokens,
                    COALESCE(SUM(cache_hit_tokens), 0)               AS
                    cache_hit_tokens,
                    COALESCE(SUM(cost_cents), 0)                     AS total_cents
                FROM usage_records
                WHERE ts >= datetime('now', ?)
                GROUP BY {group_by}
                ORDER BY total_cents DESC, calls DESC
                """,
                (self._days_param(days),),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    group_by: r["key"],
                    "calls": int(r["calls"]),
                    "input_tokens": int(r["input_tokens"]),
                    "output_tokens": int(r["output_tokens"]),
                    "cache_hit_tokens": int(r["cache_hit_tokens"]),
                    "total_tokens": int(r["input_tokens"]) + int(r["output_tokens"]),
                    "total_cents": int(r["total_cents"]),
                }
            )
        return out

    def daily(self, days: int) -> list[dict[str, Any]]:
        """按日聚合明细（报表用），含「零数据日」也补 0。"""
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                """
                SELECT
                    substr(ts, 1, 10)                                AS day,
                    COUNT(*)                                          AS calls,
                    COALESCE(SUM(input_tokens), 0)                   AS input_tokens,
                    COALESCE(SUM(output_tokens), 0)                  AS output_tokens,
                    COALESCE(SUM(cache_hit_tokens), 0)               AS
                    cache_hit_tokens,
                    COALESCE(SUM(cost_cents), 0)                     AS total_cents
                FROM usage_records
                WHERE ts >= datetime('now', ?)
                GROUP BY day
                ORDER BY day
                """,
                (self._days_param(days),),
            ).fetchall()
        # 零数据日补 0，让报表前端不用补空
        today = datetime.now(timezone.utc).date()
        days_idx = [(today - timedelta(days=i)).isoformat()
                     for i in range(days - 1, -1, -1)]
        agg: dict[str, dict[str, Any]] = {}
        for r in rows:
            agg[r["day"]] = {
                "day": r["day"],
                "calls": int(r["calls"]),
                "input_tokens": int(r["input_tokens"]),
                "output_tokens": int(r["output_tokens"]),
                "cache_hit_tokens": int(r["cache_hit_tokens"]),
                "total_tokens": int(r["input_tokens"]) + int(r["output_tokens"]),
                "total_cents": int(r["total_cents"]),
            }
        return [
            agg.get(
                d,
                {
                    "day": d,
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_hit_tokens": 0,
                    "total_tokens": 0,
                    "total_cents": 0,
                },
            )
            for d in days_idx
        ]

    # ---- 对外 API ----

    def record_usage(
        self,
        *,
        id: str,
        ts: Optional[datetime],
        plugin: str,
        user: str,
        model: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        cache_hit_tokens: int,
        session_id: Optional[str],
    ) -> tuple[UsageRecord, bool]:
        """完整记录一次 LLM 调用：算价 + 幂等写入。返回 (record, created)。"""
        prices = self.list_prices()
        price, defaulted = resolve_price(model, provider, prices)
        cost_cents = compute_cost_cents(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit_tokens=cache_hit_tokens,
            input_price=price.input_price,
            output_price=price.output_price,
            cache_hit_price=price.cache_hit_price,
        )
        rec = UsageRecord(
            id=id,
            ts=ts or datetime.now(timezone.utc),
            plugin=plugin,
            user=user,
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit_tokens=cache_hit_tokens,
            cost_cents=cost_cents,
            session_id=session_id,
            pricing_defaulted=defaulted,
        )
        # 幂等：先看 id 是否已存在；存在则返回原 record（保留第一次的费用），
        # 不存在再算价 + 插入。这才是「同 id 重复提交 = 忽略」的真正语义。
        existing = self.get_record(id)
        if existing is not None:
            return existing, False
        self.insert_record(rec)
        return rec, True

    # ---- 高级封装（api 层直接调） ----

    def summary(self, days: int) -> dict[str, Any]:
        calls, inp, out, cache, cents = self._summary(days)
        return {
            "days": days,
            "calls": calls,
            "input_tokens": inp,
            "output_tokens": out,
            "cache_hit_tokens": cache,
            "total_tokens": inp + out,
            "total_cents": cents,
        }

    def by_model(self, days: int) -> list[dict[str, Any]]:
        return self._grouped("model", days)

    def by_plugin(self, days: int) -> list[dict[str, Any]]:
        return self._grouped("plugin", days)

    def by_user(self, days: int) -> list[dict[str, Any]]:
        return self._grouped("user", days)


__all__ = ["UsageStorage"]
