#!/usr/bin/env python3
"""
P2: API 熔断器 (Circuit Breaker)
DDW AI Hub Orchestration — 长任务无人值守体系

功能：
- 检测 API 调用失败（5xx、429、超时）
- 熔断：连续 N 次失败 → 打开熔断器 → 快速失败
- 半开：冷却时间后尝试一次 → 成功则关闭，失败则继续熔断
- 支持 MiniMax / DeepSeek 等多 provider
- 降级链：主模型 → 备份模型 → 本地模型

设计：
- 经典 circuit breaker 模式（Closed → Open → Half-Open）
- 支持 per-provider 独立熔断
"""

from __future__ import annotations
import time
from enum import Enum
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from datetime import datetime


class CircuitState(str, Enum):
    CLOSED = "closed"           # 正常运行
    OPEN = "open"               # 熔断中，快速失败
    HALF_OPEN = "half_open"     # 试探恢复


# ── 默认配置 ──

DEFAULT_CONFIG = {
    "failure_threshold": 5,           # 连续 5 次失败 → 熔断
    "success_threshold": 3,           # 半开状态下连续 3 次成功 → 恢复
    "timeout_seconds": 60,            # 熔断持续时间
    "half_open_max_requests": 1,      # 半开状态下最多允许 1 个请求
    
    "providers": {
        "minimax-cn": {
            "base_url": "https://api.minimaxi.com/v1",
            "fallback": "deepseek",     # 降级链
        },
        "deepseek": {
            "base_url": "https://api.deepseek.com/v1",
            "fallback": "local",
        },
        "local": {
            "base_url": "http://127.0.0.1:11434/v1",
            "fallback": None,           # 最终兜底
        },
    },
}


# ── 故障记录 ──

@dataclass
class FailureRecord:
    timestamp: float
    error_type: str       # 5xx | 429 | timeout | connection
    status_code: int = 0
    message: str = ""


# ── 熔断器 ──

class CircuitBreaker:
    """
    API 熔断器
    
    状态机:
        CLOSED ──(连续 N 次失败)──▶ OPEN
        OPEN   ──(冷却时间后)────▶ HALF_OPEN
        HALF_OPEN ──(成功试探)────▶ CLOSED
        HALF_OPEN ──(试探失败)────▶ OPEN
    
    用法:
        cb = CircuitBreaker("minimax-cn")
        
        def call_api():
            response = requests.post(...)
            if response.status_code >= 500:
                cb.record_failure("5xx", response.status_code)
            else:
                cb.record_success()
    """
    
    def __init__(
        self,
        name: str,
        config: Dict = None,
        on_open: Callable = None,
        on_close: Callable = None,
    ):
        cfg = {**DEFAULT_CONFIG, **(config or {})}
        
        self.name = name
        self.failure_threshold = cfg["failure_threshold"]
        self.success_threshold = cfg["success_threshold"]
        self.timeout_seconds = cfg["timeout_seconds"]
        self.half_open_max_requests = cfg["half_open_max_requests"]
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0
        self.last_state_change = time.time()
        self.half_open_requests = 0
        
        self.failures: List[FailureRecord] = []
        self.total_successes = 0
        self.total_failures = 0
        
        self.on_open = on_open
        self.on_close = on_close
    
    def record_success(self):
        """记录一次成功"""
        self.total_successes += 1
        
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self._transition_to(CircuitState.CLOSED)
                if self.on_close:
                    self.on_close(self.name)
        elif self.state == CircuitState.CLOSED:
            # 成功次数重置失败计数（连续失败才熔断）
            self.failure_count = 0
    
    def record_failure(
        self,
        error_type: str = "unknown",
        status_code: int = 0,
        message: str = "",
    ):
        """记录一次失败"""
        self.total_failures += 1
        self.failure_count += 1
        self.failures.append(FailureRecord(
            timestamp=time.time(),
            error_type=error_type,
            status_code=status_code,
            message=message,
        ))
        
        # 清理旧记录
        cutoff = time.time() - 300
        self.failures = [f for f in self.failures if f.timestamp > cutoff]
        
        if self.state == CircuitState.CLOSED and self.failure_count >= self.failure_threshold:
            self._transition_to(CircuitState.OPEN)
            if self.on_open:
                self.on_open(self.name)
        
        elif self.state == CircuitState.HALF_OPEN:
            self._transition_to(CircuitState.OPEN)
            if self.on_open:
                self.on_open(self.name)
    
    def allow_request(self) -> bool:
        """是否允许发起请求"""
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            elapsed = time.time() - self.last_state_change
            if elapsed >= self.timeout_seconds:
                self._transition_to(CircuitState.HALF_OPEN)
                return True
            return False
        
        if self.state == CircuitState.HALF_OPEN:
            return self.half_open_requests < self.half_open_max_requests
    
    def _transition_to(self, new_state: CircuitState):
        """状态转换"""
        old_state = self.state
        self.state = new_state
        self.last_state_change = time.time()
        
        if new_state == CircuitState.HALF_OPEN:
            self.success_count = 0
            self.half_open_requests = 0
        
        if new_state == CircuitState.CLOSED:
            self.failure_count = 0
            self.success_count = 0
            self.half_open_requests = 0
    
    def execute(self, fn: Callable, *args, **kwargs) -> Any:
        """
        带熔断保护的执行
        
        Usage:
            result = cb.execute(lambda: requests.get(url))
        """
        if not self.allow_request():
            raise CircuitBreakerOpenError(
                f"熔断器 [{self.name}] 已断开，{self.timeout_seconds}s 后重试"
            )
        
        try:
            result = fn(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure(
                error_type="exception",
                message=str(e)[:200],
            )
            raise
    
    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN
    
    @property
    def stats(self) -> Dict:
        """当前统计"""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "recent_failures": len(self.failures),
            "last_failure": datetime.fromtimestamp(self.last_failure_time).isoformat() if self.last_failure_time else None,
            "state_age_seconds": round(time.time() - self.last_state_change, 1),
        }


class CircuitBreakerOpenError(Exception):
    """熔断器断开时抛出的异常"""
    pass


# ── 多 provider 熔断管理器 ──

class CircuitBreakerManager:
    """
    管理多个 provider 的熔断器 + 降级链
    
    用法:
        manager = CircuitBreakerManager()
        provider = manager.get_best_provider()
        # 用 provider 发起请求...
        # 失败时:
        manager.record_failure(provider, "5xx", 500)
        # 自动降级到下一个
        next_provider = manager.get_best_provider()
    """
    
    def __init__(self, config: Dict = None):
        cfg = {**DEFAULT_CONFIG, **(config or {})}
        self.provider_configs = cfg.get("providers", {})
        self.breakers: Dict[str, CircuitBreaker] = {}
        
        for name in self.provider_configs:
            self.breakers[name] = CircuitBreaker(name=name, config=cfg)
    
    def get_best_provider(self, preferred: str = None) -> Optional[str]:
        """获取当前最佳 provider（自动降级）"""
        providers = list(self.provider_configs.keys())
        
        # 优先使用指定 provider
        if preferred and preferred in providers:
            if self.breakers[preferred].allow_request():
                return preferred
            # 指定的 provider 熔断了，走降级链
            fallback = self.provider_configs[preferred].get("fallback")
            if fallback and fallback in providers:
                if self.breakers[fallback].allow_request():
                    return fallback
        
        # 找第一个可用的
        for name in providers:
            if self.breakers[name].allow_request():
                return name
        
        return None  # 全部熔断
    
    def record_success(self, provider: str):
        if provider in self.breakers:
            self.breakers[provider].record_success()
    
    def record_failure(self, provider: str, error_type: str = "", status_code: int = 0, message: str = ""):
        if provider in self.breakers:
            self.breakers[provider].record_failure(error_type, status_code, message)
    
    def get_all_stats(self) -> Dict:
        return {name: cb.stats for name, cb in self.breakers.items()}


# ── 自测 ──

if __name__ == "__main__":
    print("=== 熔断器自测 ===\n")
    
    cb = CircuitBreaker("test-provider", {
        "failure_threshold": 3,
        "success_threshold": 2,
        "timeout_seconds": 2,
    })
    
    # 模拟连续失败
    print("模拟 3 次失败...")
    for i in range(3):
        cb.record_failure("5xx", 500, f"test error {i}")
        print(f"  失败 {i+1}: state={cb.state.value}, failures={cb.failure_count}")
    
    print(f"\n熔断状态: is_open={cb.is_open}")
    print(f"允许请求: {cb.allow_request()}")
    
    # 等待冷却
    print(f"\n等待 {cb.timeout_seconds}s 冷却...")
    time.sleep(cb.timeout_seconds + 0.1)
    
    print(f"状态: {cb.state.value}")
    print(f"允许请求: {cb.allow_request()}")
    
    # 半开测试
    cb.record_success()
    print(f"成功 1: state={cb.state.value}, success_count={cb.success_count}")
    cb.record_success()
    print(f"成功 2: state={cb.state.value}, success_count={cb.success_count}")
    
    print(f"\n最终状态: {cb.stats}")
    
    # 多 provider 测试
    print(f"\n=== 多 Provider 降级测试 ===")
    manager = CircuitBreakerManager()
    
    # 熔断 minimax
    for i in range(5):
        manager.breakers["minimax-cn"].record_failure("429", 429)
    print(f"minimax 熔断: {manager.breakers['minimax-cn'].is_open}")
    
    best = manager.get_best_provider()
    print(f"最佳 provider: {best}")
    
    stats = manager.get_all_stats()
    for name, s in stats.items():
        print(f"  {name}: {s['state']}")
