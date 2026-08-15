"""
DDW AI Hub Orchestration
长任务无人值守体系

模块清单:
- schemas:      handoff_schema.py    (G2: 交接棒 schema)
- validators:   handoff_validator.py (G2: 交接棒校验器)
                scorecard.py         (G4: Scorecard 审计层)
- monitors:     watchdog.py          (P5: 死循环检测)
                token_usage.py       (P3: Token 用量监控)
                disk_watchdog.py     (P4: 磁盘水位监控)
- runtime:      dag_runtime.py       (G1: DAG 执行引擎)
                throttle.py          (G8: 监控节流器)
                circuit_breaker.py   (P2: API 熔断器)
                recovery.py          (G7: 故障恢复/清理)
                task_persist.py      (P1/P6: 持久化+checkpoint)
- orchestration: pipeline_loader.py  (G3: YAML 模板加载)
- templates:    pipeline_template.yaml  (G3: 标准流水线模板)
- scripts:      start_orchestrator.py   (一键启动)
"""

__version__ = "1.0.0"
__author__ = "DDW AI Hub"

from .schemas.handoff_schema import Handoff, HandoffStatus, FileChange, TestResult, QualityCheck
from .validators.handoff_validator import HandoffValidator, ValidationResult
from .validators.scorecard import Scorecard, ScorecardResult
from .monitors.watchdog import Watchdog
from .monitors.token_usage import TokenMonitor
from .monitors.disk_watchdog import DiskMonitor
from .runtime.dag_runtime import DAG, DAGNode, DAGRunner, create_linear_dag, create_fan_out_dag
from .runtime.throttle import Throttle, ThrottlePhase
from .runtime.circuit_breaker import CircuitBreaker, CircuitBreakerManager
from .runtime.recovery import RecoveryManager
from .runtime.task_persist import TaskPersistence
from .orchestration.pipeline_loader import PipelineLoader, Pipeline
