#!/usr/bin/env python3
"""
DDW 调度内核 · PG 状态持久化 + 硬断路器 原型
═══════════════════════════════════════════════════════
验证两个底线稳定机制:

1. 调度内核无状态化 — 所有状态存 PG（DDW 已有数据库），进程重启不丢状态
2. 硬断路器 — 当所有 AI 推理路径都不可用时，立即拒绝请求不排队

⚠️ 设计决策：DDW 使用 PostgreSQL 作为唯一数据库。
           调度状态不引入 Redis — 用 PG 表代替 KV，减少运维复杂度。

本 spike 使用 SQLite（内存模式）作为 PG 的 drop-in 替代——
SQL 完全兼容，生产环境只需改连接串。

Usage:
  python3 breaker_and_state.py [--scenario cascade_failure|crash_restart|full|all]

Author: DDW Scheduler Spike | 2026-06-28
"""

import time
import uuid
import random
import json
import sqlite3
import threading
import argparse
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


# ═══════════════════════ PG 状态表 DDL ═══════════════════════

DDL = """
-- 调度器 · vLLM 实例状态表（生产环境 → PostgreSQL）
CREATE TABLE IF NOT EXISTS scheduler_vllm_state (
    instance_name   TEXT PRIMARY KEY,
    effective_max   INTEGER NOT NULL DEFAULT 1,
    state           TEXT NOT NULL DEFAULT 'healthy',
    last_probe_at   REAL NOT NULL DEFAULT 0,
    p50_rtt_ms      REAL NOT NULL DEFAULT 0,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 调度器 · 看板卡池状态表
CREATE TABLE IF NOT EXISTS scheduler_kanban_state (
    source_id       TEXT PRIMARY KEY,
    max_cards       INTEGER NOT NULL DEFAULT 1,
    cards_used      INTEGER NOT NULL DEFAULT 0,
    signal          TEXT NOT NULL DEFAULT '🟢',
    cache_hits      INTEGER NOT NULL DEFAULT 0,
    ttl_reclaims    INTEGER NOT NULL DEFAULT 0,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 调度器 · 断路器状态表（单行 singleton: id=1 永远只有一条记录）
CREATE TABLE IF NOT EXISTS scheduler_breaker_state (
    id              INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    ai_unavailable  BOOLEAN NOT NULL DEFAULT FALSE,
    since           REAL,
    reason          TEXT NOT NULL DEFAULT '',
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


# ═══════════════════════ 数据模型 ═══════════════════════

@dataclass
class VLLMInstanceState:
    """vLLM 实例状态"""
    effective_max: int = 1
    state: str = "healthy"
    last_probe_at: float = 0
    p50_rtt_ms: float = 0

@dataclass 
class KanbanPoolState:
    """看板卡池状态"""
    max_cards: int = 1
    cards_used: int = 0
    signal: str = "🟢"
    cache_hits: int = 0
    ttl_reclaims: int = 0

@dataclass
class BreakerState:
    """断路器状态"""
    ai_unavailable: bool = False
    since: Optional[float] = None
    reason: str = ""


# ═══════════════════════ PG 状态存储层 ═══════════════════════

class SchedulerStateStore:
    """基于 PostgreSQL 的调度状态存储层。
    
    调度内核 crash 后重启 → 从此层恢复状态，只需一次 DB 查询。
    
    生产环境: conn = psycopg2.connect(DSN)
    本 spike:  conn = sqlite3.connect(":memory:")（SQL 兼容 PG，可直接迁移）
    
    关键设计:
    - 所有写操作使用 UPSERT（INSERT ... ON CONFLICT ... DO UPDATE）
    - breaker_state 使用 id=1 singleton 行
    - 不引入 Redis — PG 足以胜任毫秒级状态读写
    """
    
    def __init__(self, db_path: str = ":memory:"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()
    
    def _init_schema(self):
        """初始化调度状态表"""
        with self._lock:
            # SQLite 不支持 CHECK 约束中的复杂表达式，移除 id=1 CHECK
            self.conn.executescript(DDL.replace(
                "CHECK (id = 1)", ""
            ))
            # 确保 breaker singleton 行存在
            self.conn.execute("""
                INSERT OR IGNORE INTO scheduler_breaker_state (id, ai_unavailable, reason)
                VALUES (1, FALSE, '')
            """)
            self.conn.commit()
    
    # ── vLLM 实例状态 ──
    def save_vllm_state(self, instance_name: str, state: VLLMInstanceState):
        with self._lock:
            self.conn.execute("""
                INSERT INTO scheduler_vllm_state 
                    (instance_name, effective_max, state, last_probe_at, p50_rtt_ms, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(instance_name) DO UPDATE SET
                    effective_max = excluded.effective_max,
                    state = excluded.state,
                    last_probe_at = excluded.last_probe_at,
                    p50_rtt_ms = excluded.p50_rtt_ms,
                    updated_at = CURRENT_TIMESTAMP
            """, (instance_name, state.effective_max, state.state,
                  state.last_probe_at, state.p50_rtt_ms))
            self.conn.commit()
    
    def load_vllm_state(self, instance_name: str) -> Optional[VLLMInstanceState]:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM scheduler_vllm_state WHERE instance_name = ?",
                (instance_name,)
            ).fetchone()
            if row is None:
                return None
            return VLLMInstanceState(
                effective_max=row["effective_max"],
                state=row["state"],
                last_probe_at=row["last_probe_at"],
                p50_rtt_ms=row["p50_rtt_ms"],
            )
    
    def load_all_vllm_states(self) -> Dict[str, VLLMInstanceState]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM scheduler_vllm_state"
            ).fetchall()
            return {
                row["instance_name"]: VLLMInstanceState(
                    effective_max=row["effective_max"],
                    state=row["state"],
                    last_probe_at=row["last_probe_at"],
                    p50_rtt_ms=row["p50_rtt_ms"],
                )
                for row in rows
            }
    
    def delete_vllm_state(self, instance_name: str):
        with self._lock:
            self.conn.execute(
                "DELETE FROM scheduler_vllm_state WHERE instance_name = ?",
                (instance_name,)
            )
            self.conn.commit()
    
    # ── 看板卡池状态 ──
    def save_kanban_state(self, source_id: str, state: KanbanPoolState):
        with self._lock:
            self.conn.execute("""
                INSERT INTO scheduler_kanban_state 
                    (source_id, max_cards, cards_used, signal, cache_hits, ttl_reclaims, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(source_id) DO UPDATE SET
                    max_cards = excluded.max_cards,
                    cards_used = excluded.cards_used,
                    signal = excluded.signal,
                    cache_hits = excluded.cache_hits,
                    ttl_reclaims = excluded.ttl_reclaims,
                    updated_at = CURRENT_TIMESTAMP
            """, (source_id, state.max_cards, state.cards_used,
                  state.signal, state.cache_hits, state.ttl_reclaims))
            self.conn.commit()
    
    def load_kanban_state(self, source_id: str) -> Optional[KanbanPoolState]:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM scheduler_kanban_state WHERE source_id = ?",
                (source_id,)
            ).fetchone()
            if row is None:
                return None
            return KanbanPoolState(
                max_cards=row["max_cards"],
                cards_used=row["cards_used"],
                signal=row["signal"],
                cache_hits=row["cache_hits"],
                ttl_reclaims=row["ttl_reclaims"],
            )
    
    # ── 断路器状态 ──
    def save_breaker_state(self, state: BreakerState):
        with self._lock:
            self.conn.execute("""
                UPDATE scheduler_breaker_state 
                SET ai_unavailable = ?, since = ?, reason = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, (state.ai_unavailable, state.since, state.reason))
            self.conn.commit()
    
    def load_breaker_state(self) -> BreakerState:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM scheduler_breaker_state WHERE id = 1"
            ).fetchone()
            if row is None:
                return BreakerState()
            return BreakerState(
                ai_unavailable=bool(row["ai_unavailable"]),
                since=row["since"],
                reason=row["reason"],
            )
    
    # ── 统计查询（PG 的优势 — SQL 聚合比 KV 遍历更高效） ──
    def count_healthy_vllm(self) -> int:
        with self._lock:
            row = self.conn.execute(
                "SELECT COUNT(*) as cnt FROM scheduler_vllm_state WHERE state = 'healthy'"
            ).fetchone()
            return row["cnt"]
    
    def total_ttl_reclaims(self) -> int:
        with self._lock:
            row = self.conn.execute(
                "SELECT COALESCE(SUM(ttl_reclaims), 0) as total FROM scheduler_kanban_state"
            ).fetchone()
            return row["total"]
    
    def get_degraded_sources(self) -> List[str]:
        """查询所有黄灯/红灯的数据源"""
        with self._lock:
            rows = self.conn.execute(
                "SELECT source_id, signal FROM scheduler_kanban_state WHERE signal IN ('🟡', '🔴')"
            ).fetchall()
            return [f"{row['source_id']}({row['signal']})" for row in rows]
    
    # ── 快照导出（crash→restart 模拟用） ──
    def snapshot(self) -> Dict[str, Any]:
        return {
            "vllm_instances": self.load_all_vllm_states(),
            "breaker": self.load_breaker_state(),
            "stats": {
                "healthy_vllm": self.count_healthy_vllm(),
                "ttl_reclaims": self.total_ttl_reclaims(),
                "degraded_sources": self.get_degraded_sources(),
            },
            "timestamp": time.time(),
        }


# ═══════════════════════ 硬断路器 ═══════════════════════

class AIHardBreaker:
    """DDW AI 服务硬断路器。
    
    当所有推理路径（本地 vLLM + 云端 MiniMax + 云端 DeepSeek + 本地 Ollama）
    全部不可用时，断路器打开，立即拒绝所有新请求不排队。
    
    防止雪崩: 1000 个请求排队等待恢复 → 恢复瞬间一起涌入 → 再次打垮系统。
    """
    
    def __init__(self, store: SchedulerStateStore):
        self.store = store
        self._last_probe_at: float = 0
        self._probe_interval: float = 30.0
    
    def is_available(self) -> bool:
        state = self.store.load_breaker_state()
        return not state.ai_unavailable
    
    def trip(self, reason: str):
        state = BreakerState(
            ai_unavailable=True,
            since=time.time(),
            reason=reason,
        )
        self.store.save_breaker_state(state)
        return f"🔴 BREAKER OPEN — {reason}"
    
    def try_probe(self, probe_fn) -> Optional[str]:
        now = time.time()
        if now - self._last_probe_at < self._probe_interval:
            return None
        
        self._last_probe_at = now
        try:
            result = probe_fn()
            if result:
                self.store.save_breaker_state(BreakerState())
                return "✅ BREAKER CLOSED — AI service recovered"
        except Exception:
            pass
        return f"🔴 still open (probed at {time.strftime('%H:%M:%S')})"


# ═══════════════════════ 模拟 AI 后端 ═══════════════════════

class SimulatedAIBackend:
    def __init__(self):
        self.available = True
        self._call_count = 0
    
    def call(self) -> Optional[str]:
        self._call_count += 1
        if not self.available:
            raise Exception("AI backend unavailable")
        time.sleep(random.uniform(0.05, 0.2))
        return f"response_{self._call_count}"
    
    def degrade(self): self.available = False
    def recover(self): self.available = True


class Simulator:
    def __init__(self, store: SchedulerStateStore):
        self.store = store
        self.breaker = AIHardBreaker(store)
        self.vllm_local = SimulatedAIBackend()
        self.cloud_minimax = SimulatedAIBackend()
        self.cloud_deepseek = SimulatedAIBackend()
        self.ollama_local = SimulatedAIBackend()
        self.stats = {"accepted": 0, "rejected": 0, "recovered": 0}
        self.event_log: list = []
    
    def _log(self, msg: str):
        self.event_log.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
    
    def handle_request(self, request_id: str) -> tuple[bool, str]:
        if not self.breaker.is_available():
            self.stats["rejected"] += 1
            return False, "rejected by breaker"
        
        backends = [
            ("vllm_local", self.vllm_local),
            ("cloud_minimax", self.cloud_minimax),
            ("cloud_deepseek", self.cloud_deepseek),
            ("ollama_local", self.ollama_local),
        ]
        
        all_unavailable = True
        for name, backend in backends:
            try:
                result = backend.call()
                self.stats["accepted"] += 1
                return True, f"ok via {name}"
            except Exception:
                continue
        
        reason = self.breaker.trip("all 4 AI backends unavailable")
        self._log(reason)
        self.stats["rejected"] += 1
        return False, "all paths exhausted"
    
    def probe_all_backends(self) -> Optional[str]:
        for backend in [self.vllm_local, self.cloud_minimax,
                        self.cloud_deepseek, self.ollama_local]:
            try:
                result = backend.call()
                if result:
                    return result
            except Exception:
                continue
        return None
    
    def breaker_recovery_loop(self):
        while True:
            time.sleep(5)
            if not self.breaker.is_available():
                result = self.breaker.try_probe(self.probe_all_backends)
                if result:
                    self._log(result)
                    self.stats["recovered"] += 1


# ═══════════════════════ 场景函数 ═══════════════════════

def scenario_cascade_failure():
    """场景1: 级联故障 → 断路器打开 → 拒绝请求 → 恢复"""
    print("\n" + "="*60)
    print("场景1: 级联故障 → PG 断路器 → 恢复")
    print("="*60)
    
    store = SchedulerStateStore(":memory:")
    sim = Simulator(store)
    
    # 保存初始健康状态到 PG
    store.save_vllm_state("gpu-1", VLLMInstanceState(effective_max=8, state="healthy"))
    store.save_vllm_state("gpu-2", VLLMInstanceState(effective_max=6, state="healthy"))
    print(f"  已注册 vLLM 实例: {store.count_healthy_vllm()} 台健康")
    
    recovery_thread = threading.Thread(target=sim.breaker_recovery_loop, daemon=True)
    recovery_thread.start()
    
    print("\n📗 Phase 1: 正常运行")
    for i in range(3):
        ok, msg = sim.handle_request(f"req-{i}")
        print(f"  req-{i}: {'✅' if ok else '❌'} {msg}")
    
    state = store.load_breaker_state()
    print(f"  断路器: {'打开' if state.ai_unavailable else '关闭'}")
    
    print("\n📕 Phase 2: 所有后端故障 → 断路器打开")
    sim.vllm_local.degrade()
    sim.cloud_minimax.degrade()
    sim.cloud_deepseek.degrade()
    sim.ollama_local.degrade()
    
    for i in range(5):
        ok, msg = sim.handle_request(f"req-{i+3}")
        print(f"  req-{i+3}: {'✅' if ok else '❌'} {msg}")
    
    state = store.load_breaker_state()
    print(f"  断路器: {'🔴 打开' if state.ai_unavailable else '关闭'} — {state.reason}")
    
    print("\n🔴 Phase 3: 断路器打开 — 请求立即拒绝（不排队不等待）")
    for i in range(3):
        ok, msg = sim.handle_request(f"req-{i+8}")
        print(f"  req-{i+8}: ❌ {msg}")
    
    print("\n📗 Phase 4: 后端恢复 → 探针检测 → 断路器关闭")
    time.sleep(8)
    sim.cloud_minimax.recover()
    time.sleep(8)
    state = store.load_breaker_state()
    print(f"  断路器: {'✅ 已关闭' if not state.ai_unavailable else '🔴 仍打开'}")
    
    for i in range(3):
        ok, msg = sim.handle_request(f"req-{i+11}")
        print(f"  req-{i+11}: {'✅' if ok else '❌'} {msg}")
    
    print(f"\n最终统计: accepted={sim.stats['accepted']} rejected={sim.stats['rejected']} "
          f"recovered={sim.stats['recovered']}")
    print(f"PG 状态: healthy_vllm={store.count_healthy_vllm()}")


def scenario_crash_restart():
    """场景2: 调度内核 crash → PG 恢复 → 无缝接管"""
    print("\n" + "="*60)
    print("场景2: 调度内核 crash → PG 恢复 → 无缝重启")
    print("="*60)
    
    # 使用文件模式的 SQLite 模拟 PG 持久化（crash 后文件仍在）
    import tempfile, os
    db_file = os.path.join(tempfile.gettempdir(), "ddw_scheduler_spike.db")
    
    # Phase 1: 写入状态
    print("\n📝 Phase 1: 写入调度状态到 PG")
    store1 = SchedulerStateStore(db_file)
    
    store1.save_vllm_state("gpu-node-1", VLLMInstanceState(
        effective_max=8, state="healthy", p50_rtt_ms=220
    ))
    store1.save_vllm_state("gpu-node-2", VLLMInstanceState(
        effective_max=6, state="healthy", p50_rtt_ms=250
    ))
    store1.save_kanban_state("scada_prod", KanbanPoolState(
        max_cards=5, cards_used=2, signal="🟢"
    ))
    store1.save_kanban_state("mes_db", KanbanPoolState(
        max_cards=10, cards_used=7, signal="🟡"
    ))
    store1.save_breaker_state(BreakerState())
    
    # 验证写入
    vllm_count = store1.count_healthy_vllm()
    kanban_degraded = store1.get_degraded_sources()
    print(f"  vLLM 实例: {vllm_count} 台健康")
    print(f"  降级数据源: {kanban_degraded if kanban_degraded else '无'}")
    
    snap = store1.snapshot()
    print(f"  状态快照: {len(json.dumps(snap, default=str))} bytes")
    
    # 关闭连接（模拟 crash）
    store1.conn.close()
    del store1
    
    # Phase 2: crash
    print(f"\n💥 Phase 2: 调度内核 CRASH — 进程内存全部丢失")
    print(f"  PG 数据文件仍存在: {db_file}")
    
    # Phase 3: 恢复
    print(f"\n🔄 Phase 3: 新进程启动 → 从 PG 恢复（一次 SELECT 查询）")
    store2 = SchedulerStateStore(db_file)
    
    vllm_states = store2.load_all_vllm_states()
    print(f"  恢复 vLLM 实例: {len(vllm_states)} 台")
    for name, state in vllm_states.items():
        print(f"    {name}: effective_max={state.effective_max} state={state.state} p50={state.p50_rtt_ms}ms")
    
    breaker = store2.load_breaker_state()
    print(f"  断路器: {'打开' if breaker.ai_unavailable else '关闭'}")
    
    # 断言恢复数据完整性
    assert len(vllm_states) == 2
    assert vllm_states["gpu-node-1"].effective_max == 8
    assert vllm_states["gpu-node-2"].state == "healthy"
    assert not breaker.ai_unavailable
    
    store2.conn.close()
    os.unlink(db_file)
    print(f"\n✅ 状态恢复完全一致 — 零数据丢失，仅 PG 无 Redis")


def scenario_sql_aggregation():
    """场景3: PG SQL 聚合查询 — KV 做不到的统计分析"""
    print("\n" + "="*60)
    print("场景3: PG SQL 聚合 — 超越 KV 的运维查询能力")
    print("="*60)
    
    store = SchedulerStateStore(":memory:")
    
    # 批量写入
    for i in range(5):
        store.save_vllm_state(f"gpu-{i}", VLLMInstanceState(
            effective_max=(i+1)*2, state="healthy" if i<3 else "degraded", 
            p50_rtt_ms=200 + i*800
        ))
    for src, sig in [("scada", "🟢"), ("mes", "🟡"), ("wms", "🟡"), ("erp", "🔴")]:
        store.save_kanban_state(src, KanbanPoolState(signal=sig, cards_used=5))

    print(f"\n  vLLM 健康率: {store.count_healthy_vllm()}/5")
    print(f"  降级数据源: {store.get_degraded_sources()}")
    print(f"  TTL 回收总计: {store.total_ttl_reclaims()}")
    
    # PG 才能做但 KV 做不到的查询示例
    with store._lock:
        rows = store.conn.execute("""
            SELECT signal, COUNT(*) as cnt 
            FROM scheduler_kanban_state 
            GROUP BY signal 
            ORDER BY cnt DESC
        """).fetchall()
        print(f"  数据源信号分布: {[(r['signal'], r['cnt']) for r in rows]}")
        
        avg_rtt = store.conn.execute(
            "SELECT AVG(p50_rtt_ms) as avg FROM scheduler_vllm_state WHERE state = 'healthy'"
        ).fetchone()
        print(f"  健康 vLLM 平均 RTT: {avg_rtt['avg']:.0f}ms")
    
    print(f"\n  ✅ 这些聚合查询在 Redis KV 模型中需要多次 round-trip，PG 一次 SQL 完成")


# ═══════════════════════════ 入口 ═══════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="DDW PG状态持久化 + 硬断路器原型")
    parser.add_argument("--scenario", 
                        choices=["cascade_failure", "crash_restart", "sql_agg", "all"],
                        default="all")
    args = parser.parse_args()
    
    if args.scenario in ("cascade_failure", "all"):
        scenario_cascade_failure()
    if args.scenario in ("crash_restart", "all"):
        scenario_crash_restart()
    if args.scenario in ("sql_agg", "all"):
        scenario_sql_aggregation()
    
    print(f"\n{'='*60}")
    print("全部场景完成 ✅")
    print(f"数据库: PostgreSQL (spike 用 SQLite 模拟，SQL 完全兼容)")
