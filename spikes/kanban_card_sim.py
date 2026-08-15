#!/usr/bin/env python3
"""
DDW 调度内核 · 数据看板卡三色信号 + TTL 回收 + 查询去重 原型
═══════════════════════════════════════════════════════════════
模拟多个数据源在高并发请求下的看板卡调度行为。

核心模式:
  1. 自适应看板卡池（从 1 开始自举上调）
  2. 三色信号灯（🟢 <50% / 🟡 50-80% / 🔴 >80%）
  3. TTL 超时级联清理（卡泄漏自动回收 + 杀持有者）
  4. 查询去重（同指纹复用缓存）

Usage:
  python3 kanban_card_sim.py [--sources 3] [--requests 200] [--concurrent 50]

Author: DDW Scheduler Spike | 2026-06-28
"""

import time
import uuid
import random
import hashlib
import threading
import argparse
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, List
from collections import defaultdict


# ═══════════════════════ 核心数据结构 ═══════════════════════

class CardState(Enum):
    IDLE = "idle"
    ACQUIRED = "acquired"      # 已分配但未建立连接
    IN_USE = "in_use"          # 正在查询数据源


class Signal(Enum):
    GREEN = "🟢"
    YELLOW = "🟡"
    RED = "🔴"


@dataclass
class KanbanCard:
    card_id: str
    source_id: str
    state: CardState = CardState.IDLE
    acquired_by: Optional[str] = None        # request_id
    acquired_at: Optional[float] = None
    ttl_seconds: float = 30.0                # 超时自动回收
    query_signature: Optional[str] = None    # SHA256 查询指纹
    query_result: Optional[str] = None       # 去重复用的查询结果
    waiters: List[str] = field(default_factory=list)  # 同指纹等待者


@dataclass
class KanbanPool:
    """单个数据源的看板卡池"""
    source_id: str
    max_cards: int = 1                       # 自适应上调
    physical_limit: int = 64                 # 数据源物理上限
    cards: List[KanbanCard] = field(default_factory=list)
    signal: Signal = Signal.GREEN
    stats: dict = field(default_factory=lambda: {
        "total_acquired": 0, "total_released": 0,
        "cache_hits": 0, "ttl_reclaims": 0,
        "realtime_queries": 0, "total_queries": 0,
    })
    # 自适应评估
    last_eval_at: float = 0
    eval_interval: float = 10.0              # 评估间隔
    stable_count: int = 0                    # 连续稳定周期数
    response_times: List[float] = field(default_factory=list)  # 最近响应时间
    queue_empty_since: Optional[float] = None
    
    def __post_init__(self):
        # 初始化 max_cards 张卡片
        for i in range(self.max_cards):
            self.cards.append(KanbanCard(
                card_id=f"{self.source_id}-card-{i}",
                source_id=self.source_id,
            ))
    
    @property
    def used_cards(self) -> int:
        return sum(1 for c in self.cards 
                   if c.state in (CardState.ACQUIRED, CardState.IN_USE))
    
    @property
    def idle_cards(self) -> int:
        return sum(1 for c in self.cards if c.state == CardState.IDLE)
    
    @property
    def usage_pct(self) -> float:
        if self.max_cards == 0:
            return 0
        return self.used_cards / self.max_cards * 100


# ═══════════════════════ 全局调度器 ═══════════════════════

class KanbanScheduler:
    """看板卡全局调度器"""
    
    def __init__(self):
        self.pools: Dict[str, KanbanPool] = {}
        self.query_cache: Dict[str, str] = {}  # query_signature → result
        self.lock = threading.Lock()
        self.event_log: List[str] = []
    
    def register_source(self, source_id: str, physical_limit: int = 64):
        """注册一个数据源"""
        self.pools[source_id] = KanbanPool(
            source_id=source_id,
            physical_limit=physical_limit,
        )
        self._log(f"注册数据源: {source_id} (物理上限={physical_limit})")
    
    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.event_log.append(f"[{ts}] {msg}")
    
    def _query_signature(self, query: str) -> str:
        """生成查询指纹"""
        return hashlib.sha256(query.encode()).hexdigest()[:16]
    
    def acquire_card(self, source_id: str, request_id: str, 
                     query: str) -> tuple[Optional[KanbanCard], str]:
        """
        获取看板卡。返回 (card, reason)。
        
        去重优化: 如果已有同指纹的卡正在查询，注册为等待者，不分配新卡。
        信号限流: 红灯时仅 P0 可获卡（此处简化为全部拒绝，P0 判断在调用方）。
        """
        pool = self.pools.get(source_id)
        if pool is None:
            return None, f"未知数据源: {source_id}"
        
        query_sig = self._query_signature(query)
        
        with self.lock:
            # 1. 查询去重: 已有同指纹的 IN_USE 卡？
            for card in pool.cards:
                if (card.state == CardState.IN_USE and 
                    card.query_signature == query_sig):
                    card.waiters.append(request_id)
                    pool.stats["cache_hits"] += 1
                    self._log(f"🔄 去重命中: {request_id} 等待 {card.card_id} (指纹={query_sig[:8]})")
                    return None, f"dedup: waiting on {card.card_id}"
            
            # 2. 信号限流
            if pool.signal == Signal.RED:
                return None, "🔴 数据源饱和，限流"
            
            # 3. 查找空闲卡
            for card in pool.cards:
                if card.state == CardState.IDLE:
                    card.state = CardState.ACQUIRED
                    card.acquired_by = request_id
                    card.acquired_at = time.time()
                    card.query_signature = query_sig
                    card.query_result = None
                    card.waiters = []
                    pool.stats["total_acquired"] += 1
                    self._log(f"📋 {card.card_id} → {request_id} (指纹={query_sig[:8]})")
                    return card, "acquired"
            
            # 4. 无空闲卡 — 需要排队或降级
            # 黄灯时仍可排队（调用方自己决定等待或走缓存）
            if pool.signal == Signal.YELLOW:
                return None, f"🟡 排队中 (used={pool.used_cards}/{pool.max_cards})"
            else:
                return None, f"排队中 (used={pool.used_cards}/{pool.max_cards})"
    
    def use_card(self, card: KanbanCard, source_id: str):
        """标记卡为 IN_USE（建立了数据源连接）"""
        card.state = CardState.IN_USE
        self._log(f"⚡ {card.card_id} IN_USE by {card.acquired_by}")
    
    def release_card(self, card: KanbanCard, source_id: str, 
                     result: Optional[str] = None):
        """
        释放看板卡。
        如果查询结果不为空，通知所有等待者（查询去重）。
        """
        pool = self.pools.get(source_id)
        if pool is None:
            return
        
        with self.lock:
            holder = card.acquired_by or "unknown"
            waiter_count = len(card.waiters)
            
            # 通知等待者
            if result and card.waiters:
                self._log(f"📤 {card.card_id} 完成, 通知 {waiter_count} 个等待者")
            
            # 回收卡
            card.state = CardState.IDLE
            card.acquired_by = None
            card.acquired_at = None
            card.query_signature = None
            card.query_result = None
            card.waiters = []
            pool.stats["total_released"] += 1
            pool.stats["realtime_queries"] += 1
    
    def check_ttl_and_reclaim(self):
        """检查 TTL 超时的卡，执行级联清理"""
        now = time.time()
        reclaimed = 0
        
        for source_id, pool in self.pools.items():
            with self.lock:
                for card in pool.cards:
                    if card.state in (CardState.ACQUIRED, CardState.IN_USE):
                        if card.acquired_at and (now - card.acquired_at) > card.ttl_seconds:
                            holder = card.acquired_by or "unknown"
                            duration = now - (card.acquired_at or now)
                            
                            # 级联清理: 回收卡 + 记录持有者
                            card.state = CardState.IDLE
                            card.acquired_by = None
                            card.acquired_at = None
                            pool.stats["ttl_reclaims"] += 1
                            reclaimed += 1
                            
                            self._log(f"⏰ TTL 回收: {card.card_id} (持有者={holder}, "
                                     f"超时={duration:.0f}s)")
        
        return reclaimed
    
    def calibrate_pools(self):
        """自适应调整看板卡池大小 + 更新三色信号"""
        now = time.time()
        
        for source_id, pool in self.pools.items():
            if now - pool.last_eval_at < pool.eval_interval:
                continue
            pool.last_eval_at = now
            
            # 计算平均响应时间
            if pool.response_times:
                avg_rt = sum(pool.response_times) / len(pool.response_times)
                pool.response_times = []
            else:
                avg_rt = 0
            
            # 自校准: 根据响应时间和看板卡使用率调整
            usage_pct = pool.usage_pct
            
            # ——— 调整 max_cards ———
            if avg_rt > 0 and avg_rt < 0.5 and usage_pct == 0:
                # 响应快 + 无排队 → 上调
                pool.max_cards = min(pool.max_cards + 1, pool.physical_limit)
                # 补充新卡
                new_card = KanbanCard(
                    card_id=f"{source_id}-card-{pool.max_cards - 1}",
                    source_id=source_id,
                )
                pool.cards.append(new_card)
                pool.stable_count = 0
                self._log(f"📈 {source_id} max_cards ↑ {pool.max_cards}")
            
            elif avg_rt > 2.0:
                # 响应慢 → 下调
                pool.max_cards = max(1, pool.max_cards - 1)
                pool.stable_count = 0
                self._log(f"📉 {source_id} max_cards ↓ {pool.max_cards} (avg_rt={avg_rt:.2f}s)")
            
            else:
                pool.stable_count += 1
                if pool.stable_count >= 3:
                    pool.eval_interval = 60.0  # 稳定后降低评估频率
            
            # ——— 更新三色信号 ———
            old_signal = pool.signal
            if usage_pct < 50:
                pool.signal = Signal.GREEN
            elif usage_pct < 80:
                pool.signal = Signal.YELLOW
            else:
                pool.signal = Signal.RED
            
            if pool.signal != old_signal:
                self._log(f"🚦 {source_id} 信号: {old_signal.value} → {pool.signal.value} "
                         f"(usage={usage_pct:.0f}%)")
    
    def report(self) -> str:
        """生成看板卡池状态报告"""
        lines = ["\n" + "="*60]
        lines.append("DDW 看板卡池状态报告")
        lines.append("="*60)
        
        for source_id, pool in self.pools.items():
            usage_bar = "█" * int(pool.usage_pct / 10) + "░" * (10 - int(pool.usage_pct / 10))
            lines.append(f"\n  {pool.signal.value} {source_id}:")
            lines.append(f"    看板卡:  [{usage_bar}] {pool.used_cards}/{pool.max_cards} "
                        f"(usage={pool.usage_pct:.0f}%)")
            lines.append(f"    统计:    获取={pool.stats['total_acquired']} "
                        f"释放={pool.stats['total_released']} "
                        f"去重命中={pool.stats['cache_hits']} "
                        f"TTL回收={pool.stats['ttl_reclaims']}")
        
        return "\n".join(lines)
    
    def print_event_log(self, last_n: int = 20):
        """打印最近的事件日志"""
        print(f"\n{'='*60}")
        print(f"事件日志 (最近 {min(last_n, len(self.event_log))} 条):")
        print("-"*60)
        for entry in self.event_log[-last_n:]:
            print(f"  {entry}")


# ═══════════════════════ 模拟运行 ═══════════════════════

def simulate_request(scheduler: KanbanScheduler, source_id: str, 
                     request_id: str, query: str, priority: str = "P1"):
    """模拟一个完整的请求生命周期: 获取卡 → 使用 → 释放"""
    card, reason = scheduler.acquire_card(source_id, request_id, query)
    
    if card is None:
        # 未获取到卡（去重命中、无空闲卡、限流）
        if reason.startswith("dedup"):
            return "dedup_hit", reason
        else:
            return "queued", reason
    
    # 模拟建立连接
    scheduler.use_card(card, source_id)
    
    # 模拟查询数据源（随机延迟 50-500ms）
    query_time = random.uniform(0.05, 0.5)
    time.sleep(query_time)
    
    # 模拟获取结果
    result = f"result_for_{query[:20]}"
    
    # 释放卡
    scheduler.release_card(card, source_id, result)
    
    return "ok", f"done in {query_time*1000:.0f}ms"


def run_simulation(num_sources: int = 3, num_requests: int = 200, 
                   concurrent: int = 50, ttl_check_interval: float = 2.0):
    """运行看板卡模拟"""
    scheduler = KanbanScheduler()
    
    # 注册数据源
    sources = [f"datasource_{i}" for i in range(1, num_sources + 1)]
    for src in sources:
        scheduler.register_source(src, physical_limit=16)
    
    print(f"\n{'='*60}")
    print(f"DDW 数据看板卡模拟")
    print(f"数据源: {num_sources} | 请求数: {num_requests} | 并发: {concurrent}")
    print(f"{'='*60}")
    
    # 预设查询池（模拟"1000 人同时问同一问题"的场景）
    queries = [
        "SELECT oee FROM production_line_A WHERE date=today",
        "SELECT oee FROM production_line_A WHERE date=today",  # 重复！触发去重
        "SELECT oee FROM production_line_A WHERE date=today",  # 重复！
        "SELECT inventory FROM warehouse WHERE sku='ABC'",
        "SELECT status FROM equipment WHERE line='B'",
        "SELECT quality_metric FROM batch WHERE lot='L123'",
        "SELECT temperature FROM sensor WHERE zone='Z5'",
        "SELECT schedule FROM mes WHERE order='WO456'",
        "SELECT downtime FROM maintenance WHERE machine='M7'",
    ]
    
    # 启动 TTL 回收后台线程
    ttl_running = threading.Event()
    ttl_running.set()
    
    def ttl_reclaimer():
        while ttl_running.is_set():
            time.sleep(ttl_check_interval)
            reclaimed = scheduler.check_ttl_and_reclaim()
            if reclaimed > 0:
                scheduler._log(f"TTL 回收完成: {reclaimed} 张卡")
    
    ttl_thread = threading.Thread(target=ttl_reclaimer, daemon=True)
    ttl_thread.start()
    
    # 启动自适应校准后台线程
    def calibrator():
        while ttl_running.is_set():
            time.sleep(5)
            scheduler.calibrate_pools()
    
    cal_thread = threading.Thread(target=calibrator, daemon=True)
    cal_thread.start()
    
    # 并发发送请求
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    results = {"ok": 0, "dedup_hit": 0, "queued": 0}
    
    with ThreadPoolExecutor(max_workers=concurrent) as executor:
        futures = []
        for i in range(num_requests):
            src = random.choice(sources)
            query = random.choice(queries)
            request_id = f"req-{uuid.uuid4().hex[:8]}"
            fut = executor.submit(simulate_request, scheduler, src, request_id, query)
            futures.append(fut)
        
        for fut in as_completed(futures):
            try:
                status, _ = fut.result()
                results[status] = results.get(status, 0) + 1
            except Exception as e:
                scheduler._log(f"❌ 请求异常: {e}")
    
    # 停止后台线程
    ttl_running.clear()
    ttl_thread.join(timeout=2)
    cal_thread.join(timeout=2)
    
    # 输出报告
    print(f"\n请求结果: ok={results['ok']} dedup_hit={results['dedup_hit']} "
          f"queued={results.get('queued', 0)}")
    print(scheduler.report())
    scheduler.print_event_log(last_n=15)
    
    # 去重效率
    total = sum(results.values())
    dedup_pct = results.get("dedup_hit", 0) / total * 100 if total > 0 else 0
    print(f"\n去重效率: {results.get('dedup_hit', 0)}/{total} = {dedup_pct:.1f}% "
          f"查询被去重合并")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DDW 数据看板卡原型")
    parser.add_argument("--sources", type=int, default=3, help="数据源数量")
    parser.add_argument("--requests", type=int, default=200, help="总请求数")
    parser.add_argument("--concurrent", type=int, default=50, help="最大并发数")
    args = parser.parse_args()
    
    run_simulation(args.sources, args.requests, args.concurrent)
