#!/usr/bin/env python3
"""
DDW 调度内核 · vLLM RTT 自校准探针原型
═══════════════════════════════════════════════
模拟 vLLM 实例的负载变化，验证 RTT 探针自校准算法。

核心思路：
  不读 vLLM 的 max_num_seqs，用探针 RTT 自行推导 effective_max_concurrent。

故障场景：
  - 正常: RTT 稳定 200ms → effective_max 逐步上调
  - 劣化: RTT 从 200ms 升到 5000ms → 检测到 degraded → 摘除
  - 恢复: RTT 回落到 200ms → 逐步放回池中

Usage:
  python3 rtt_probe_calibrate.py [--scenario normal|degraded|recovery]

Author: DDW Scheduler Spike | 2026-06-28
"""

import time
import random
import argparse
from dataclasses import dataclass, field
from collections import deque
from typing import Optional


# ═══════════════════════════ 配置 ═══════════════════════════

@dataclass
class ProbeConfig:
    """探针配置"""
    probe_interval: float = 5.0          # 探针间隔（秒）
    probe_prompt: str = "ping"           # 固定探针 prompt（永不变化）
    probe_max_tokens: int = 10           # 探针固定 max_tokens
    
    # RTT 阈值
    rtt_healthy_ms: float = 500          # RTT < 此值 = 健康
    rtt_slow_ms: float = 2000            # RTT > 此值 = 偏慢，下调
    rtt_degraded_ms: float = 5000        # RTT > 此值 = 劣化，摘除
    
    # 自校准参数
    calibrate_step: int = 1              # 每次上调步长
    degraded_cooldown: float = 60.0      # 劣化摘除后冷却期（秒）
    recovery_retry: float = 30.0         # 恢复重试间隔（秒）
    
    # 持续性检测
    degraded_duration: float = 12.0      # 劣化需持续超过此时间才触发摘除
    window_size: int = 30                # 滑动窗口大小


# ═══════════════════════════ 模拟 vLLM 实例 ═══════════════════════════

class SimulatedVLLM:
    """模拟一个 vLLM 推理实例，返回模拟 RTT"""
    
    def __init__(self, name: str, base_rtt_ms: float = 200, scenario: str = "normal"):
        self.name = name
        self.base_rtt = base_rtt_ms
        self.scenario = scenario
        self.degraded_at: Optional[float] = None
        self.recovered_at: Optional[float] = None
        self.start_time = time.time()
        
    def get_rtt(self) -> float:
        """返回模拟 RTT（毫秒）"""
        elapsed = time.time() - self.start_time
        
        if self.scenario == "normal":
            return self.base_rtt + random.uniform(-50, 100)
        
        elif self.scenario == "degraded":
            # 前 10 秒正常，之后持续劣化
            if elapsed < 10:
                return self.base_rtt + random.uniform(-50, 100)
            else:
                if self.degraded_at is None:
                    self.degraded_at = elapsed
                return 5000 + random.uniform(-500, 2000)
        
        elif self.scenario == "recovery":
            # 0-10s 正常, 10-30s 劣化, 30s+ 恢复
            if elapsed < 10:
                return self.base_rtt + random.uniform(-50, 100)
            elif elapsed < 30:
                if self.degraded_at is None:
                    self.degraded_at = elapsed
                return 5000 + random.uniform(-500, 2000)
            else:
                if self.recovered_at is None:
                    self.recovered_at = elapsed
                return self.base_rtt + random.uniform(-50, 100)
        
        return self.base_rtt


# ═══════════════════════════ RTT 滑动窗口 ═══════════════════════════

@dataclass
class RTTWindow:
    """RTT 滑动窗口 — 维护最近 N 次探针的 RTT"""
    values: deque = field(default_factory=deque)
    
    def add(self, rtt_ms: float, max_size: int = 30):
        self.values.append(rtt_ms)
        if len(self.values) > max_size:
            self.values.popleft()
    
    def p50(self) -> float:
        if not self.values:
            return 0
        sorted_vals = sorted(self.values)
        mid = len(sorted_vals) // 2
        return sorted_vals[mid]
    
    def p95(self) -> float:
        if not self.values:
            return 0
        sorted_vals = sorted(self.values)
        idx = int(len(sorted_vals) * 0.95)
        return sorted_vals[min(idx, len(sorted_vals) - 1)]
    
    def is_empty(self) -> bool:
        return len(self.values) == 0


# ═══════════════════════════ vLLM 实例状态机 ═══════════════════════════

class InstanceState:
    HEALTHY = "healthy"       # 正常服务
    WATCHING = "watching"     # 检测到 spike，观察中
    DEGRADED = "degraded"     # 确认劣化，已摘除，等待冷却
    PROBE = "probe"           # 冷却期结束，发探针测试恢复
    FAILED = "failed"         # 多次探针失败，需要人工介入


@dataclass
class VLLMInstance:
    """DDW 调度层对单个 vLLM 实例的抽象"""
    name: str
    simulator: SimulatedVLLM
    config: ProbeConfig
    
    # 自校准状态
    effective_max: int = 1              # 自校准后的有效并发上限
    physical_max: int = 256             # vLLM 物理 max_num_seqs
    state: str = InstanceState.HEALTHY
    rtt_window: RTTWindow = field(default_factory=RTTWindow)
    
    # 劣化追踪
    degraded_since: Optional[float] = None
    cooldown_until: Optional[float] = None
    last_probe_at: float = 0
    
    def probe(self) -> float:
        """发送探针，返回 RTT（ms）"""
        rtt = self.simulator.get_rtt()
        self.rtt_window.add(rtt, self.config.window_size)
        self.last_probe_at = time.time()
        return rtt
    
    def calibrate(self) -> dict:
        """自校准: 评估当前状态并调整 effective_max
        
        状态机流转:
          HEALTHY → (spike detected) → WATCHING
          WATCHING → (12s sustained) → DEGRADED
          WATCHING → (rtt recovers) → HEALTHY (false alarm)
          DEGRADED → (cooldown ends) → PROBE
          PROBE → (rtt < 500ms) → HEALTHY
          PROBE → (rtt still bad) → DEGRADED (re-cool)
          DEGRADED → (3 次探针失败) → FAILED (人工介入)
        """
        now = time.time()
        p50 = self.rtt_window.p50()
        result = {
            "name": self.name,
            "state": self.state,
            "effective_max": self.effective_max,
            "p50_rtt_ms": round(p50, 1),
            "action": "hold",
        }
        
        # ═══════ HEALTHY: 正常服务 + 劣化检测 ═══════
        if self.state == InstanceState.HEALTHY:
            self.degraded_since = None
            
            # 检测到 spike?
            if p50 > self.config.rtt_degraded_ms:
                self.state = InstanceState.WATCHING
                self.degraded_since = now
                result["action"] = f"⚠️ WATCHING: spike detected (p50={p50:.0f}ms)"
                result["state"] = self.state
                return result
            
            # 正常自校准
            if p50 < self.config.rtt_healthy_ms:
                if self.effective_max < self.physical_max:
                    self.effective_max += self.config.calibrate_step
                    result["action"] = f"↑ increase to {self.effective_max}"
                    result["effective_max"] = self.effective_max
                    return result
            
            elif p50 > self.config.rtt_slow_ms:
                if self.effective_max > 1:
                    self.effective_max = max(1, self.effective_max - self.config.calibrate_step)
                    result["action"] = f"↓ decrease to {self.effective_max}"
                    result["effective_max"] = self.effective_max
                    return result
            
            result["action"] = "hold (rtt stable)"
            return result
        
        # ═══════ WATCHING: 观察 spike 是否持续 ═══════
        if self.state == InstanceState.WATCHING:
            # RTT 恢复了 → 假警报
            if p50 < self.config.rtt_slow_ms:
                self.state = InstanceState.HEALTHY
                self.degraded_since = None
                result["action"] = "✅ recovered (false alarm)"
                result["state"] = self.state
                return result
            
            # 仍在劣化中
            degraded_duration = now - (self.degraded_since or now)
            if degraded_duration > self.config.degraded_duration:
                # 持续劣化 → 确认摘除
                self.state = InstanceState.DEGRADED
                self.cooldown_until = now + self.config.degraded_cooldown
                self.degraded_since = None
                self.effective_max = 0
                result["action"] = "⛔ DEGRADED — instance removed from pool"
                result["state"] = self.state
                result["effective_max"] = 0
                return result
            
            result["action"] = f"watching... ({degraded_duration:.0f}s/{self.config.degraded_duration}s)"
            return result
        
        # ═══════ DEGRADED: 摘除中，等待冷却 ═══════
        if self.state == InstanceState.DEGRADED:
            if self.cooldown_until and now < self.cooldown_until:
                remaining = self.cooldown_until - now
                result["action"] = f"⏳ cooldown ({remaining:.0f}s remaining)"
                result["effective_max"] = 0
                return result
            
            # 冷却结束 → 进入探针模式
            self.state = InstanceState.PROBE
            self._failed_probes = getattr(self, '_failed_probes', 0)
            result["action"] = "🔍 PROBE: sending recovery test..."
            result["state"] = self.state
            # 不发探针，下一轮再发（让探针间隔生效）
            return result
        
        # ═══════ PROBE: 发探针测试是否恢复 ═══════
        if self.state == InstanceState.PROBE:
            rtt = self.probe()
            
            if rtt < self.config.rtt_healthy_ms:
                # 恢复！逐步放回池中
                self.state = InstanceState.HEALTHY
                self.effective_max = 1  # 从1开始重新校准
                self.cooldown_until = None
                self.degraded_since = None
                self._failed_probes = 0
                result["action"] = "✅ RECOVERED → back to HEALTHY (effective_max=1)"
                result["state"] = self.state
                result["effective_max"] = self.effective_max
                return result
            
            # 仍未恢复
            self._failed_probes = getattr(self, '_failed_probes', 0) + 1
            if self._failed_probes >= 3:
                self.state = InstanceState.FAILED
                result["action"] = "💀 FAILED — requires manual intervention"
                result["state"] = self.state
                result["effective_max"] = 0
                return result
            
            # 重新冷却
            self.state = InstanceState.DEGRADED
            self.cooldown_until = now + self.config.degraded_cooldown
            result["action"] = f"❌ still degraded (probe #{self._failed_probes}/3), re-cooldown"
            result["state"] = self.state
            result["effective_max"] = 0
            return result
        
        # ═══════ FAILED: 需要人工介入 ═══════
        if self.state == InstanceState.FAILED:
            result["action"] = "💀 FAILED — manual recovery required"
            result["effective_max"] = 0
            return result
        
        result["action"] = "unknown state"
        return result


# ═══════════════════════════ 模拟运行 ═══════════════════════════

def run_simulation(scenario: str, duration: float = 60):
    """运行探针自校准模拟"""
    config = ProbeConfig()
    simulator = SimulatedVLLM("vllm-instance-1", base_rtt_ms=200, scenario=scenario)
    instance = VLLMInstance("vllm-instance-1", simulator, config)
    
    print(f"\n{'='*60}")
    print(f"DDW vLLM RTT 自校准探针模拟")
    print(f"场景: {scenario} | 时长: {duration}s | 探针间隔: {config.probe_interval}s")
    print(f"{'='*60}")
    print(f"{'Time':>6s} | {'State':>10s} | {'P50 RTT':>8s} | {'Eff.Max':>8s} | Action")
    print("-" * 70)
    
    start = time.time()
    
    while time.time() - start < duration:
        # 在 PROBE 状态下，calibrate() 内部会发探针，不需要额外发
        if instance.state != InstanceState.PROBE:
            instance.probe()
        
        # 自校准
        cal = instance.calibrate()
        
        elapsed = time.time() - start
        print(f"{elapsed:5.0f}s | {cal['state']:>10s} | {cal['p50_rtt_ms']:6.0f}ms | "
              f"{cal['effective_max']:>4}/{instance.physical_max} | {cal['action']}")
        
        # 等待下一次探针
        time.sleep(config.probe_interval)
    
    # 最终状态
    print(f"\n{'='*60}")
    print(f"最终状态:")
    print(f"  实例状态: {instance.state}")
    print(f"  有效并发: {instance.effective_max}/{instance.physical_max}")
    print(f"  P50 RTT:  {instance.rtt_window.p50():.0f}ms")
    print(f"  P95 RTT:  {instance.rtt_window.p95():.0f}ms")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DDW vLLM RTT 自校准探针原型")
    parser.add_argument("--scenario", choices=["normal", "degraded", "recovery"],
                        default="normal", help="模拟场景")
    parser.add_argument("--duration", type=float, default=60,
                        help="模拟时长（秒）")
    args = parser.parse_args()
    
    run_simulation(args.scenario, args.duration)
