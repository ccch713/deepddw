#!/usr/bin/env python3
"""
DDW AI Hub Orchestration — 一键启动脚本
长任务无人值守体系总入口

用法:
    python3 start_orchestrator.py [--mode monitor|execute|recover]

模式:
    monitor   — 仅启动监控（watchdog + token + disk）
    execute   — 执行指定 pipeline
    recover   — 自动恢复孤儿任务
    all       — 全部启动（默认）
"""

import sys
import os
import argparse
from pathlib import Path

# 确保模块可导入
sys.path.insert(0, str(Path(__file__).parent))

from monitors.watchdog import Watchdog
from monitors.token_usage import TokenMonitor, quick_token_report
from monitors.disk_watchdog import DiskMonitor, quick_disk_check
from runtime.throttle import Throttle
from runtime.circuit_breaker import CircuitBreakerManager
from runtime.recovery import RecoveryManager, preflight_check, quick_preflight
from runtime.task_persist import TaskPersistence, auto_recover_on_startup
from runtime.dag_runtime import DAGRunner, DAG, DAGNode, create_linear_dag, NodeType
from orchestration.pipeline_loader import PipelineLoader, load_and_run
from validators.handoff_validator import HandoffValidator
from validators.scorecard import Scorecard
from schemas.handoff_schema import Handoff


def mode_monitor():
    """仅启动监控"""
    print("🔍 启动监控模式...")
    
    # 1. 健康检查
    print("\n=== 环境健康检查 ===")
    print(quick_preflight())
    
    # 2. 磁盘检查
    print("\n=== 磁盘监控 ===")
    dm = DiskMonitor()
    print(dm.generate_report())
    
    # 3. Token 用量
    print("\n=== Token 用量 ===")
    print(quick_token_report())
    
    # 4. Watchdog 状态
    wd = Watchdog()
    status = wd.get_status()
    print(f"\n=== Watchdog ===")
    print(f"活跃任务: {status['tasks']}")
    print(f"24h 告警: {status['alerts_24h']}")
    wd.close()


def mode_execute():
    """执行 Pipeline"""
    print("🚀 启动执行模式...")
    
    # 1. 健康检查
    health = preflight_check()
    if not health["ok"]:
        print("⚠️ 环境问题:")
        for issue in health["issues"]:
            print(f"  ❌ {issue}")
        return
    
    # 2. 加载模板
    loader = PipelineLoader()
    templates = loader.list_templates()
    print(f"可用模板: {templates}")
    
    if not templates:
        print("❌ 无可用模板")
        return
    
    # 3. 构建并显示 DAG
    pipeline = loader.load(templates[0])
    dag = pipeline.build_dag()
    print(f"\nPipeline: {pipeline.name} v{pipeline.version}")
    print(dag.to_mermaid())
    
    print("\n✅ DAG 就绪，等待任务分配...")


def mode_recover():
    """恢复孤儿任务"""
    print("🔄 启动恢复模式...")
    
    recovered = auto_recover_on_startup()
    
    if recovered:
        print(f"✅ 已恢复 {len(recovered)} 个任务:")
        for task in recovered:
            print(f"  - {task['task_id']} (step {task['step_number']})")
    else:
        print("✅ 无孤儿任务需要恢复")
    
    # 查看恢复历史
    tp = TaskPersistence()
    history = tp.get_recovery_history()
    if history:
        print(f"\n近期恢复记录 ({len(history)} 条):")
        for h in history[:5]:
            print(f"  [{h['event']}] {h['task_id']}: {h['details']}")
    tp.close()


def mode_all():
    """全部模式"""
    mode_monitor()
    print("\n" + "=" * 60)
    mode_recover()
    print("\n" + "=" * 60)
    mode_execute()


def main():
    parser = argparse.ArgumentParser(
        description="DDW AI Hub Orchestration — 长任务无人值守体系",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["monitor", "execute", "recover", "all"],
        default="all",
        help="运行模式",
    )
    parser.add_argument(
        "--template",
        default="pipeline_template.yaml",
        help="Pipeline 模板文件名",
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("DDW AI Hub Orchestration v1.0")
    print("长任务无人值守体系")
    print("=" * 60)
    
    if args.mode == "monitor":
        mode_monitor()
    elif args.mode == "execute":
        mode_execute()
    elif args.mode == "recover":
        mode_recover()
    else:
        mode_all()


if __name__ == "__main__":
    main()
