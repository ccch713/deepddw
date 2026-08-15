#!/usr/bin/env python3
"""
G8: 监控节流器
DDW AI Hub Orchestration — 长任务无人值守体系

功能：
- 自适应轮询间隔：启动时 5s → 稳定期 30s → 长任务 60s+
- 只上报状态变化（不每次都 dump 全量信息）
- 令牌桶算法控制 API 调用频率
- 支持多级节流策略

设计：
- 按阶段配置间隔
- 状态变化检测（diff 驱动上报）
- 令牌桶限制监控 API 调用
"""

from __future__ import annotations
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class ThrottlePhase(str, Enum):
    STARTUP = "startup"      # 刚启动，5s 高频
    ACTIVE = "active"        # 稳定运行，30s
    STEADY = "steady"        # 长跑中，60s
    COOLDOWN = "cooldown"    # 冷却期，120s
    ERROR = "error"          # 出错重试，10s


# ── 阶段配置 ──

PHASE_CONFIGS = {
    ThrottlePhase.STARTUP:  {"interval": 5,   "max_duration": 60},    # 1 分钟
    ThrottlePhase.ACTIVE:   {"interval": 30,  "max_duration": 600},   # 10 分钟
    ThrottlePhase.STEADY:   {"interval": 60,  "max_duration": 3600},  # 1 小时
    ThrottlePhase.COOLDOWN: {"interval": 120, "max_duration": 1800},  # 30 分钟
    ThrottlePhase.ERROR:    {"interval": 10,  "max_duration": 120},   # 2 分钟
}


# ── 令牌桶 ──

@dataclass
class TokenBucket:
    """简单的令牌桶，控制 API 调用频率"""
    rate: float          # 每秒生成令牌数
    capacity: int        # 桶容量
    tokens: float = 0.0
    last_refill: float = 0.0
    
    def __post_init__(self):
        self.tokens = self.capacity
        self.last_refill = time.time()
    
    def consume(self, tokens: int = 1) -> bool:
        """尝试消费令牌"""
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
    
    def wait_time(self, tokens: int = 1) -> float:
        """需要等待多少秒才能消费"""
        if self.tokens >= tokens:
            return 0
        return (tokens - self.tokens) / self.rate


# ── 状态变化检测器 ──

class StateDiff:
    """
    状态变化检测
    
    只上报变化的部分，避免每次 dump 全量状态。
    """
    
    def __init__(self):
        self._last_state: Dict[str, Any] = {}
    
    def diff(self, current: Dict[str, Any]) -> Dict[str, Any]:
        """返回与上次相比的变化"""
        if not self._last_state:
            self._last_state = current
            return {"_new": True, **current}
        
        changes = {}
        for key, value in current.items():
            if key not in self._last_state or self._last_state[key] != value:
                changes[key] = {
                    "old": self._last_state.get(key),
                    "new": value,
                }
        
        # 检查删除的键
        for key in self._last_state:
            if key not in current:
                changes[key] = {"old": self._last_state[key], "new": None}
        
        self._last_state = current
        return changes


# ── 节流器 ──

class Throttle:
    """
    监控节流器
    
    用法:
        th = Throttle()
        th.start("task-001")
        
        while True:
            if th.should_report():
                status = get_current_status()
                diff = th.get_diff(status)
                if diff:
                    send_report(diff)
            time.sleep(th.next_interval())
    """
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.phase = ThrottlePhase.STARTUP
        self.phase_start = time.time()
        self.state_diff = StateDiff()
        self.bucket = TokenBucket(rate=0.5, capacity=10)  # 0.5 req/s, 最大突发 10
        self._last_report_time = 0.0
        self._report_count = 0
        self._start_time = 0.0
    
    def start(self, task_id: str = ""):
        """开始监控一个任务"""
        self._start_time = time.time()
        self._report_count = 0
        self.transition(ThrottlePhase.STARTUP)
    
    def transition(self, phase: ThrottlePhase):
        """切换阶段"""
        if phase != self.phase:
            self.phase = phase
            self.phase_start = time.time()
    
    @property
    def interval(self) -> float:
        """当前轮询间隔（秒）"""
        return PHASE_CONFIGS[self.phase]["interval"]
    
    def update_phase(self):
        """根据运行时间和阶段时长自动切换"""
        elapsed = time.time() - self.phase_start
        max_dur = PHASE_CONFIGS[self.phase]["max_duration"]
        
        if self.phase == ThrottlePhase.STARTUP and elapsed > max_dur:
            self.transition(ThrottlePhase.ACTIVE)
        elif self.phase == ThrottlePhase.ACTIVE and elapsed > max_dur:
            self.transition(ThrottlePhase.STEADY)
        elif self.phase == ThrottlePhase.ERROR and elapsed > max_dur:
            self.transition(ThrottlePhase.ACTIVE)
    
    def should_report(self, force: bool = False) -> bool:
        """是否应该上报（检查令牌 + 间隔）"""
        self.update_phase()
        
        if not self.bucket.consume():
            return False
        
        now = time.time()
        if now - self._last_report_time < self.interval and not force:
            return False
        
        self._last_report_time = now
        self._report_count += 1
        return True
    
    def get_diff(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """获取状态变化（自动去重）"""
        return self.state_diff.diff(state)
    
    def next_interval(self) -> float:
        """建议的下次轮询等待时间"""
        return max(1.0, self.interval)
    
    def mark_error(self):
        """标记出错"""
        self.transition(ThrottlePhase.ERROR)
    
    def mark_recovery(self):
        """标记恢复"""
        self.transition(ThrottlePhase.ACTIVE)
    
    @property
    def stats(self) -> Dict:
        """统计信息"""
        elapsed = time.time() - self._start_time
        return {
            "phase": self.phase.value,
            "phase_elapsed_seconds": round(time.time() - self.phase_start, 1),
            "total_elapsed_seconds": round(elapsed, 1),
            "report_count": self._report_count,
            "interval": self.interval,
            "tokens_available": round(self.bucket.tokens, 1),
        }


# ── 自测 ──

if __name__ == "__main__":
    th = Throttle()
    th.start("test-task")
    
    print("=== 节流器自测 ===")
    
    # 模拟多轮
    for i in range(5):
        print(f"\n轮 {i+1}: phase={th.phase.value}, interval={th.interval}s")
        
        if th.should_report():
            state = {"step": i, "status": "running", "cpu": 45 + i}
            diff = th.get_diff(state)
            print(f"  上报: {diff}")
        
        print(f"  stats: {th.stats}")
        time.sleep(0.1)  # 模拟时间推进
    
    # 模拟出错
    th.mark_error()
    print(f"\n出错后: phase={th.phase.value}, interval={th.interval}s")
    
    # 模拟恢复
    th.mark_recovery()
    print(f"恢复后: phase={th.phase.value}, interval={th.interval}s")
    
    # 令牌桶测试
    print(f"\n令牌桶测试: tokens={th.bucket.tokens:.1f}")
    for _ in range(5):
        ok = th.bucket.consume()
        print(f"  consume: {ok}, tokens left: {th.bucket.tokens:.1f}")
