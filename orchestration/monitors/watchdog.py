#!/usr/bin/env python3
"""
P5: Watchdog 死循环/卡死检测
DDW AI Hub Orchestration — 长任务无人值守体系

功能：
- 监控正在运行的 agent 任务
- 检测死循环、卡死、超时
- 自动 kill + 通知编排者
- 支持配置：超时阈值、最大重试次数、步数上限

设计：
- 独立进程，周期性轮询 task_proxy / agentmemory 状态
- 使用 SQLite 记录每个 task 的最后活跃时间
- 超时 → 发送 kill 信号 → 通知编排者
"""

from __future__ import annotations
import os
import signal
import sqlite3
import time
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


# ── 默认配置 ──

DEFAULT_CONFIG = {
    "db_path": "~/.hermes/orchestration/watchdog.db",
    "check_interval_seconds": 10,       # 轮询间隔
    "task_timeout_seconds": 1800,        # 单个任务超时（30 分钟）
    "stall_timeout_seconds": 300,        # 停滞超时（5 分钟无活动）
    "max_retries_per_task": 3,           # 最大重试次数
    "max_inner_steps": 200,              # 单任务最大步数
    "alert_webhook": "",                 # 告警 webhook（可选）
}

DB_PATH = Path(os.path.expanduser(DEFAULT_CONFIG["db_path"]))


# ── 数据库初始化 ──

def init_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """初始化 watchdog 数据库"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            agent_id TEXT,
            status TEXT DEFAULT 'running',
            started_at TEXT,
            last_active_at TEXT,
            step_count INTEGER DEFAULT 0,
            retry_count INTEGER DEFAULT 0,
            pid INTEGER,
            workspace TEXT,
            task_type TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            alert_type TEXT,
            message TEXT,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS checkpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            step_number INTEGER,
            snapshot TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    return conn


# ── Watchdog 核心 ──

@dataclass
class TaskState:
    task_id: str
    agent_id: str = ""
    status: str = "running"
    started_at: str = ""
    last_active_at: str = ""
    step_count: int = 0
    retry_count: int = 0
    pid: int = 0
    workspace: str = ""


class Watchdog:
    """
    任务看门狗
    
    用法:
        wd = Watchdog()
        wd.register_task("task-001", agent_id="coder-1", pid=12345)
        wd.heartbeat("task-001", step_count=10)
        wd.run_once()  # 单次扫描
        
        # 或作为守护进程
        wd.run_forever()
    """
    
    def __init__(self, config: Dict = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.db_path = Path(os.path.expanduser(self.config["db_path"]))
        self.conn = init_db(self.db_path)
    
    def register_task(
        self,
        task_id: str,
        agent_id: str = "",
        pid: int = 0,
        workspace: str = "",
        task_type: str = "",
    ) -> None:
        """注册新任务"""
        now = datetime.now().isoformat()
        self.conn.execute(
            """INSERT OR REPLACE INTO tasks 
               (task_id, agent_id, status, started_at, last_active_at, pid, workspace, task_type)
               VALUES (?, ?, 'running', ?, ?, ?, ?, ?)""",
            (task_id, agent_id, now, now, pid, workspace, task_type),
        )
        self.conn.commit()
    
    def heartbeat(self, task_id: str, step_count: int = 0) -> None:
        """更新任务心跳（agent 周期性调用）"""
        now = datetime.now().isoformat()
        self.conn.execute(
            "UPDATE tasks SET last_active_at = ?, step_count = ? WHERE task_id = ?",
            (now, step_count, task_id),
        )
        self.conn.commit()
    
    def mark_completed(self, task_id: str, status: str = "completed") -> None:
        """标记任务完成"""
        now = datetime.now().isoformat()
        self.conn.execute(
            "UPDATE tasks SET status = ?, last_active_at = ? WHERE task_id = ?",
            (status, now, task_id),
        )
        self.conn.commit()
    
    def check_task(self, task_id: str, state: TaskState) -> List[Dict]:
        """检查单个任务是否异常"""
        alerts = []
        now = datetime.now()
        
        # 1. 超时检查
        if state.started_at:
            started = datetime.fromisoformat(state.started_at)
            elapsed = (now - started).total_seconds()
            if elapsed > self.config["task_timeout_seconds"]:
                alerts.append({
                    "task_id": task_id,
                    "type": "timeout",
                    "message": f"任务超时（已运行 {elapsed:.0f}s，阈值 {self.config['task_timeout_seconds']}s）",
                    "severity": "critical",
                })
        
        # 2. 停滞检查
        if state.last_active_at and state.status == "running":
            last_active = datetime.fromisoformat(state.last_active_at)
            stale = (now - last_active).total_seconds()
            if stale > self.config["stall_timeout_seconds"]:
                alerts.append({
                    "task_id": task_id,
                    "type": "stalled",
                    "message": f"任务停滞（{stale:.0f}s 无活动，阈值 {self.config['stall_timeout_seconds']}s）",
                    "severity": "critical",
                })
        
        # 3. 重试次数检查
        if state.retry_count >= self.config["max_retries_per_task"]:
            alerts.append({
                "task_id": task_id,
                "type": "max_retries",
                "message": f"超过最大重试次数（{state.retry_count}/{self.config['max_retries_per_task']}）",
                "severity": "critical",
            })
        
        # 4. 步数检查
        if state.step_count > self.config["max_inner_steps"]:
            alerts.append({
                "task_id": task_id,
                "type": "excessive_steps",
                "message": f"步数异常（{state.step_count} 步，阈值 {self.config['max_inner_steps']}）疑似死循环",
                "severity": "warning",
            })
        
        return alerts
    
    def kill_task(self, task_id: str, pid: int = 0) -> bool:
        """终止卡死任务"""
        killed = False
        
        # 通过 PID
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                killed = True
            except (ProcessLookupError, PermissionError):
                pass
        
        # 通过 task_proxy API
        # TODO: 调用 task_proxy 的 cancel 接口
        
        self.mark_completed(task_id, "killed")
        
        # 记录告警
        self.conn.execute(
            "INSERT INTO alerts (task_id, alert_type, message, created_at) VALUES (?, ?, ?, ?)",
            (task_id, "killed", f"任务被终止 (pid={pid})", datetime.now().isoformat()),
        )
        self.conn.commit()
        
        return killed
    
    def run_once(self) -> List[Dict]:
        """单次扫描，返回告警列表"""
        all_alerts = []
        
        cursor = self.conn.execute(
            "SELECT task_id, agent_id, status, started_at, last_active_at, step_count, retry_count, pid, workspace FROM tasks WHERE status = 'running'"
        )
        
        for row in cursor:
            state = TaskState(
                task_id=row[0],
                agent_id=row[1],
                status=row[2],
                started_at=row[3] or "",
                last_active_at=row[4] or "",
                step_count=row[5] or 0,
                retry_count=row[6] or 0,
                pid=row[7] or 0,
                workspace=row[8] or "",
            )
            
            alerts = self.check_task(row[0], state)
            
            for alert in alerts:
                self.conn.execute(
                    "INSERT INTO alerts (task_id, alert_type, message, created_at) VALUES (?, ?, ?, ?)",
                    (alert["task_id"], alert["type"], alert["message"], datetime.now().isoformat()),
                )
                
                # 严重告警 → 自动 kill
                if alert["severity"] == "critical" and state.pid:
                    self.kill_task(alert["task_id"], state.pid)
                    alert["action"] = "killed"
            
            all_alerts.extend(alerts)
        
        self.conn.commit()
        return all_alerts
    
    def run_forever(self) -> None:
        """守护模式：持续监控"""
        print(f"[watchdog] 启动，轮询间隔 {self.config['check_interval_seconds']}s")
        print(f"[watchdog] DB: {self.db_path}")
        
        while True:
            try:
                alerts = self.run_once()
                if alerts:
                    print(f"[watchdog] {datetime.now().strftime('%H:%M:%S')} {len(alerts)} 条告警:")
                    for a in alerts:
                        print(f"  [{a['type']}] {a['task_id']}: {a['message']}")
            except Exception as e:
                print(f"[watchdog] 扫描异常: {e}")
            
            time.sleep(self.config["check_interval_seconds"])
    
    def get_status(self) -> Dict:
        """获取当前监控状态"""
        cursor = self.conn.execute(
            "SELECT status, COUNT(*) FROM tasks GROUP BY status"
        )
        task_stats = {row[0]: row[1] for row in cursor}
        
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE created_at > ?",
            ((datetime.now() - timedelta(hours=24)).isoformat(),),
        )
        alert_count = cursor.fetchone()[0]
        
        return {
            "tasks": task_stats,
            "alerts_24h": alert_count,
            "db_path": str(self.db_path),
        }
    
    def close(self):
        self.conn.close()


# ── 便捷函数 ──

def quick_watchdog_scan(db_path: str = None) -> List[Dict]:
    """快速单次扫描"""
    config = DEFAULT_CONFIG.copy()
    if db_path:
        config["db_path"] = db_path
    wd = Watchdog(config)
    try:
        return wd.run_once()
    finally:
        wd.close()


# ── 自测 ──

if __name__ == "__main__":
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Path(tmpdir) / "test_watchdog.db"
        
        wd = Watchdog({"db_path": str(db), "task_timeout_seconds": 1, "stall_timeout_seconds": 1})
        
        # 注册一个"超时"任务
        wd.register_task("task-dead", agent_id="coder-1", pid=99999)
        # 模拟 2 秒前启动
        wd.conn.execute(
            "UPDATE tasks SET started_at = ? WHERE task_id = ?",
            ((datetime.now() - timedelta(seconds=2)).isoformat(), "task-dead"),
        )
        wd.conn.commit()
        
        # 扫描
        alerts = wd.run_once()
        print(f"=== Watchdog 自测 ({len(alerts)} 条告警) ===")
        for a in alerts:
            print(f"  [{a['type']}] {a['task_id']}: {a['message']}")
        
        # 状态
        status = wd.get_status()
        print(f"\n状态: {json.dumps(status, ensure_ascii=False, indent=2)}")
        
        wd.close()
