#!/usr/bin/env python3
"""
P1+P6: 任务状态持久化 + Checkpoint 快照恢复
DDW AI Hub Orchestration — 长任务无人值守体系

功能：
- SQLite 持久化所有 running tasks 的状态
- Hermes 崩溃/重启后自动恢复未完成任务
- Checkpoint 机制：每完成一步写快照
- 断电/断网后从最近 checkpoint 恢复

设计：
- tasks 表：当前所有任务状态
- checkpoints 表：历史快照（滚动保留最近 10 个）
- recovery_log：恢复操作日志
"""

from __future__ import annotations
import json
import os
import sqlite3
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


# ── 配置 ──

DB_PATH = Path(os.path.expanduser("~/.hermes/orchestration/task_state.db"))
MAX_CHECKPOINTS_PER_TASK = 10


# ── 数据库 ──

def init_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            pipeline_name TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            updated_at TEXT,
            started_at TEXT,
            finished_at TEXT,
            node_states TEXT,            -- JSON: {node_id: {status, started_at, ...}}
            handoff_data TEXT,            -- JSON: 最新 handoff
            config TEXT,                  -- JSON: 任务配置
            error TEXT,
            pid INTEGER,
            hostname TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS checkpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            step_number INTEGER,
            node_id TEXT,
            snapshot TEXT,                -- JSON: 完整任务快照
            created_at TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(task_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recovery_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            event TEXT,                  -- 'crashed' | 'recovered' | 'checkpoint_restored' | 'abandoned'
            details TEXT,
            created_at TEXT
        )
    """)
    # 索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_checkpoints_task ON checkpoints(task_id, step_number)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_recovery_task ON recovery_log(task_id)")
    conn.commit()
    return conn


# ── Task Persistence Manager ──

class TaskPersistence:
    """
    任务持久化管理器
    
    用法:
        tp = TaskPersistence()
        
        # 注册任务
        tp.register_task("task-001", pipeline_name="标准流水线")
        
        # 更新状态
        tp.update_node_state("task-001", "coder", {"status": "running", "started_at": now})
        
        # 创建 checkpoint
        tp.create_checkpoint("task-001", step_number=3, node_id="coder")
        
        # 恢复
        orphaned = tp.find_orphaned_tasks()
        for task in orphaned:
            tp.recover_task(task["task_id"])
    """
    
    def __init__(self, db_path: str = None):
        self.db_path = Path(db_path or DB_PATH)
        self.conn = init_db(self.db_path)
    
    def register_task(
        self,
        task_id: str,
        pipeline_name: str = "",
        config: Dict = None,
        pid: int = None,
    ) -> None:
        """注册新任务"""
        now = datetime.now().isoformat()
        self.conn.execute(
            """INSERT OR REPLACE INTO tasks 
               (task_id, pipeline_name, status, created_at, updated_at, config, pid, hostname)
               VALUES (?, ?, 'pending', ?, ?, ?, ?, ?)""",
            (
                task_id,
                pipeline_name,
                now,
                now,
                json.dumps(config or {}),
                pid or os.getpid(),
                os.uname().nodename,
            ),
        )
        self.conn.commit()
    
    def update_status(self, task_id: str, status: str, error: str = None) -> None:
        """更新任务状态"""
        now = datetime.now().isoformat()
        updates = {"status": status, "updated_at": now}
        if status == "running":
            updates["started_at"] = now
        elif status in ("completed", "failed", "killed"):
            updates["finished_at"] = now
        
        sql = "UPDATE tasks SET "
        params = []
        for k, v in updates.items():
            sql += f"{k} = ?, "
            params.append(v)
        sql = sql.rstrip(", ")
        sql += " WHERE task_id = ?"
        params.append(task_id)
        
        if error:
            sql = sql.replace("WHERE", f", error = ? WHERE")
            params.insert(-1, error[:500])
        
        self.conn.execute(sql, params)
        self.conn.commit()
    
    def update_node_state(
        self,
        task_id: str,
        node_id: str,
        node_state: Dict[str, Any],
    ) -> None:
        """更新单个节点的状态"""
        now = datetime.now().isoformat()
        
        # 读取当前 node_states
        cursor = self.conn.execute(
            "SELECT node_states FROM tasks WHERE task_id = ?", (task_id,)
        )
        row = cursor.fetchone()
        if not row:
            return
        
        node_states = json.loads(row[0]) if row[0] else {}
        node_states[node_id] = {**node_states.get(node_id, {}), **node_state, "updated_at": now}
        
        self.conn.execute(
            "UPDATE tasks SET node_states = ?, updated_at = ? WHERE task_id = ?",
            (json.dumps(node_states), now, task_id),
        )
        self.conn.commit()
    
    def save_handoff(self, task_id: str, handoff_data: Dict) -> None:
        """保存交接棒数据"""
        now = datetime.now().isoformat()
        self.conn.execute(
            "UPDATE tasks SET handoff_data = ?, updated_at = ? WHERE task_id = ?",
            (json.dumps(handoff_data), now, task_id),
        )
        self.conn.commit()
    
    def get_task(self, task_id: str) -> Optional[Dict]:
        """获取单个任务"""
        cursor = self.conn.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        )
        row = cursor.fetchone()
        if row:
            return self._row_to_dict(row)
        return None
    
    def find_orphaned_tasks(self) -> List[Dict]:
        """查找孤儿任务（running 但进程已死）"""
        cursor = self.conn.execute(
            "SELECT * FROM tasks WHERE status = 'running'"
        )
        orphaned = []
        for row in cursor:
            task = self._row_to_dict(row)
            pid = task.get("pid", 0)
            
            # 检查进程是否还活着
            if pid:
                try:
                    os.kill(pid, 0)  # 信号 0 只检查存在
                except (ProcessLookupError, PermissionError):
                    orphaned.append(task)
            else:
                # 没有 PID 信息，按更新时间判断
                updated = task.get("updated_at", "")
                if updated:
                    try:
                        last = datetime.fromisoformat(updated)
                        if (datetime.now() - last) > timedelta(minutes=10):
                            orphaned.append(task)
                    except (ValueError, TypeError):
                        pass
        
        return orphaned
    
    def create_checkpoint(
        self,
        task_id: str,
        step_number: int,
        node_id: str = "",
    ) -> int:
        """创建任务快照"""
        task = self.get_task(task_id)
        if not task:
            return -1
        
        now = datetime.now().isoformat()
        
        # 清理旧 checkpoint（保留最近 MAX_CHECKPOINTS_PER_TASK 个）
        self.conn.execute(
            """DELETE FROM checkpoints WHERE task_id = ? AND id NOT IN (
                SELECT id FROM checkpoints WHERE task_id = ?
                ORDER BY step_number DESC LIMIT ?
            )""",
            (task_id, task_id, MAX_CHECKPOINTS_PER_TASK - 1),
        )
        
        snapshot = json.dumps({
            "task": task,
            "node_id": node_id,
            "step_number": step_number,
        })
        
        cursor = self.conn.execute(
            "INSERT INTO checkpoints (task_id, step_number, node_id, snapshot, created_at) VALUES (?, ?, ?, ?, ?)",
            (task_id, step_number, node_id, snapshot, now),
        )
        self.conn.commit()
        return cursor.lastrowid
    
    def get_latest_checkpoint(self, task_id: str) -> Optional[Dict]:
        """获取最近的 checkpoint"""
        cursor = self.conn.execute(
            "SELECT * FROM checkpoints WHERE task_id = ? ORDER BY step_number DESC LIMIT 1",
            (task_id,),
        )
        row = cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "task_id": row[1],
                "step_number": row[2],
                "node_id": row[3],
                "snapshot": json.loads(row[4]),
                "created_at": row[5],
            }
        return None
    
    def recover_task(self, task_id: str) -> Dict:
        """
        从最近 checkpoint 恢复任务
        
        Returns:
            恢复结果 {restored, step_number, checkpoint_id}
        """
        checkpoint = self.get_latest_checkpoint(task_id)
        if not checkpoint:
            self._log_recovery(task_id, "recovery_failed", "无 checkpoint 可用")
            return {"restored": False, "reason": "无 checkpoint"}
        
        # 恢复任务状态
        snapshot = checkpoint["snapshot"]
        task_data = snapshot.get("task", {})
        
        self.conn.execute(
            "UPDATE tasks SET status = 'pending', updated_at = ?, node_states = ?, error = NULL WHERE task_id = ?",
            (datetime.now().isoformat(), json.dumps(task_data.get("node_states", {})), task_id),
        )
        self.conn.commit()
        
        self._log_recovery(
            task_id,
            "recovered",
            f"从 checkpoint #{checkpoint['id']} (step {checkpoint['step_number']}) 恢复",
        )
        
        return {
            "restored": True,
            "step_number": checkpoint["step_number"],
            "checkpoint_id": checkpoint["id"],
            "node_id": checkpoint["node_id"],
        }
    
    def mark_crashed(self, task_id: str) -> None:
        """标记任务为崩溃"""
        self._log_recovery(task_id, "crashed", "进程异常终止")
        self.update_status(task_id, "pending")
    
    def _log_recovery(self, task_id: str, event: str, details: str) -> None:
        self.conn.execute(
            "INSERT INTO recovery_log (task_id, event, details, created_at) VALUES (?, ?, ?, ?)",
            (task_id, event, details, datetime.now().isoformat()),
        )
        self.conn.commit()
    
    def get_recovery_history(self, task_id: str = None) -> List[Dict]:
        """获取恢复历史"""
        if task_id:
            cursor = self.conn.execute(
                "SELECT * FROM recovery_log WHERE task_id = ? ORDER BY created_at DESC LIMIT 20",
                (task_id,),
            )
        else:
            cursor = self.conn.execute(
                "SELECT * FROM recovery_log ORDER BY created_at DESC LIMIT 50"
            )
        
        return [
            {"id": r[0], "task_id": r[1], "event": r[2], "details": r[3], "created_at": r[4]}
            for r in cursor
        ]
    
    def get_status_summary(self) -> Dict:
        """获取所有任务状态摘要"""
        cursor = self.conn.execute(
            "SELECT status, COUNT(*) FROM tasks GROUP BY status"
        )
        status_counts = {r[0]: r[1] for r in cursor}
        
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'running'"
        )
        running = cursor.fetchone()[0]
        
        orphaned = len(self.find_orphaned_tasks())
        
        return {
            "total": sum(status_counts.values()),
            "by_status": status_counts,
            "running": running,
            "orphaned": orphaned,
            "db_path": str(self.db_path),
        }
    
    def _row_to_dict(self, row) -> Dict:
        cols = ["task_id", "pipeline_name", "status", "created_at", "updated_at",
                "started_at", "finished_at", "node_states", "handoff_data", "config",
                "error", "pid", "hostname"]
        d = {cols[i]: row[i] for i in range(len(row)) if i < len(cols)}
        # 解析 JSON 字段
        for field in ["node_states", "handoff_data", "config"]:
            if d.get(field) and isinstance(d[field], str):
                try:
                    d[field] = json.loads(d[field])
                except json.JSONDecodeError:
                    pass
        return d
    
    def close(self):
        self.conn.close()


# ── 启动时自动恢复 ──

def auto_recover_on_startup() -> List[Dict]:
    """
    在 Hermes 启动时调用：查找孤儿任务并恢复
    
    用法（放在 Hermes 启动脚本中）:
        from task_persist import auto_recover_on_startup
        recovered = auto_recover_on_startup()
        for task in recovered:
            print(f"恢复任务: {task['task_id']} 从 step {task['step_number']}")
    """
    tp = TaskPersistence()
    try:
        orphaned = tp.find_orphaned_tasks()
        recovered = []
        
        for task in orphaned:
            task_id = task["task_id"]
            result = tp.recover_task(task_id)
            if result["restored"]:
                recovered.append({"task_id": task_id, **result})
            else:
                tp.mark_crashed(task_id)
        
        return recovered
    finally:
        tp.close()


# ── 自测 ──

if __name__ == "__main__":
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Path(tmpdir) / "test_task.db"
        tp = TaskPersistence(str(db))
        
        # 注册任务
        tp.register_task("task-001", pipeline_name="标准流水线", pid=99999)
        tp.update_status("task-001", "running")
        
        # 更新节点状态
        tp.update_node_state("task-001", "coder", {"status": "running"})
        tp.update_node_state("task-001", "coder", {"status": "success", "files": ["a.py"]})
        
        # 创建 checkpoint
        tp.create_checkpoint("task-001", step_number=1, node_id="coder")
        tp.create_checkpoint("task-001", step_number=2, node_id="tester")
        
        # 获取状态
        task = tp.get_task("task-001")
        print(f"=== Task Persistence 自测 ===")
        print(f"任务状态: {task['status']}")
        print(f"节点状态: {json.dumps(task['node_states'], ensure_ascii=False)}")
        
        # 查找 orphan（PID 99999 不存在）
        orphaned = tp.find_orphaned_tasks()
        print(f"孤儿任务: {len(orphaned)} 个")
        
        # 恢复
        if orphaned:
            result = tp.recover_task("task-001")
            print(f"恢复结果: {result}")
        
        # 摘要
        summary = tp.get_status_summary()
        print(f"\n状态摘要: {json.dumps(summary, ensure_ascii=False, indent=2)}")
        
        tp.close()
