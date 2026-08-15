#!/usr/bin/env python3
"""
P3: Token 用量监控
DDW AI Hub Orchestration — 长任务无人值守体系

功能：
- 监控 MiniMax / DeepSeek API 的 token 消耗
- 按日/周/月统计
- 预算告警（余额 < 阈值 → 降级到低成本模型）
- 集成 aliyun_billing_pull.sh 的账单数据
- 输出 JSON 供 dashboard 使用
"""

from __future__ import annotations
import json
import os
import time
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

# ── 配置 ──

DB_PATH = Path(os.path.expanduser("~/.hermes/orchestration/token_usage.db"))

# 模型价格（¥/1M tokens）2026-06 官方定价
PRICING = {
    "minimax-m3":        {"input": 2.2, "output": 8.7, "name": "MiniMax M3"},
    "minimax-m2.7":      {"input": 2.2, "output": 8.7, "name": "MiniMax M2.7"},
    "deepseek-v4-pro":   {"input": 3.2, "output": 6.4, "name": "DeepSeek V4 Pro"},
    "deepseek-v4-flash": {"input": 0.5, "output": 2.0, "name": "DeepSeek V4 Flash"},
    "local-coder":       {"input": 0.0, "output": 0.0, "name": "Local coder-v2:16b"},
}

# 订阅/余额配置
MONTHLY_BUDGET_CNY = 119.0        # MiniMax 月度订阅
DAILY_BUDGET_CNY = MONTHLY_BUDGET_CNY / 30
BALANCE_LOW_THRESHOLD = 20.0      # 余额 < ¥20 告警
BALANCE_CRITICAL_THRESHOLD = 5.0  # 余额 < ¥5 → 强制降级


# ── 数据库 ──

def init_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            model TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cost_rmb REAL,
            session_id TEXT,
            task_id TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_summary (
            date TEXT PRIMARY KEY,
            model TEXT,
            total_input INTEGER,
            total_output INTEGER,
            total_cost REAL,
            api_calls INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS budget_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            alert_type TEXT,
            message TEXT,
            current_balance REAL,
            resolved INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn


# ── Token 追踪器 ──

@dataclass
class UsageRecord:
    timestamp: str
    model: str
    input_tokens: int
    output_tokens: int
    session_id: str = ""
    task_id: str = ""
    
    @property
    def cost_rmb(self) -> float:
        """计算费用（¥）"""
        pricing = PRICING.get(self.model, PRICING["minimax-m3"])
        cost = (self.input_tokens / 1_000_000) * pricing["input"] + \
               (self.output_tokens / 1_000_000) * pricing["output"]
        return round(cost, 6)


class TokenMonitor:
    """
    Token 用量监控
    
    用法:
        tm = TokenMonitor()
        tm.log_usage("minimax-m3", input_tokens=5000, output_tokens=2000, session_id="abc")
        
        status = tm.get_status()
        print(f"今日消耗: ¥{status['today_cost']:.2f}")
    """
    
    def __init__(self, db_path: str = None):
        self.db_path = Path(db_path or DB_PATH)
        self.conn = init_db(self.db_path)
    
    def log_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        session_id: str = "",
        task_id: str = "",
    ) -> float:
        """记录一次 API 调用"""
        now = datetime.now().isoformat()
        record = UsageRecord(
            timestamp=now,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            session_id=session_id,
            task_id=task_id,
        )
        
        self.conn.execute(
            "INSERT INTO usage_log (timestamp, model, input_tokens, output_tokens, cost_rmb, session_id, task_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now, model, input_tokens, output_tokens, record.cost_rmb, session_id, task_id),
        )
        self.conn.commit()
        return record.cost_rmb
    
    def get_today_summary(self) -> Dict:
        """今日用量摘要"""
        today = datetime.now().strftime("%Y-%m-%d")
        cursor = self.conn.execute(
            """SELECT model, SUM(input_tokens), SUM(output_tokens), SUM(cost_rmb), COUNT(*)
               FROM usage_log WHERE date(timestamp) = ? GROUP BY model""",
            (today,),
        )
        
        models = {}
        total_cost = 0.0
        total_input = 0
        total_output = 0
        total_calls = 0
        
        for row in cursor:
            model, inp, out, cost, calls = row
            inp = inp or 0
            out = out or 0
            cost = cost or 0.0
            models[model] = {
                "input_tokens": inp,
                "output_tokens": out,
                "cost_rmb": round(cost, 4),
                "api_calls": calls,
            }
            total_cost += cost
            total_input += inp
            total_output += out
            total_calls += calls
        
        return {
            "date": today,
            "total_cost_rmb": round(total_cost, 4),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_api_calls": total_calls,
            "daily_budget_rmb": round(DAILY_BUDGET_CNY, 2),
            "remaining_budget_rmb": round(DAILY_BUDGET_CNY - total_cost, 2),
            "budget_pct_used": round((total_cost / DAILY_BUDGET_CNY * 100), 1) if DAILY_BUDGET_CNY > 0 else 0,
            "by_model": models,
        }
    
    def get_week_summary(self) -> Dict:
        """本周用量摘要"""
        today = datetime.now()
        week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
        
        cursor = self.conn.execute(
            """SELECT model, SUM(input_tokens), SUM(output_tokens), SUM(cost_rmb), COUNT(*)
               FROM usage_log WHERE date(timestamp) >= ? GROUP BY model""",
            (week_start,),
        )
        
        total_cost = 0.0
        models = {}
        for row in cursor:
            model, inp, out, cost, calls = row
            cost = cost or 0.0
            models[model] = {
                "input_tokens": inp or 0,
                "output_tokens": out or 0,
                "cost_rmb": round(cost, 4),
                "api_calls": calls or 0,
            }
            total_cost += cost
        
        return {
            "week_start": week_start,
            "total_cost_rmb": round(total_cost, 4),
            "weekly_budget_rmb": round(MONTHLY_BUDGET_CNY / 4.33, 2),
            "by_model": models,
        }
    
    def check_balance(self, current_balance: float = None) -> Dict:
        """检查余额是否告警"""
        today_summary = self.get_today_summary()
        
        alerts = []
        level = "ok"
        
        if current_balance is not None:
            if current_balance <= BALANCE_CRITICAL_THRESHOLD:
                level = "critical"
                alerts.append({
                    "type": "balance_critical",
                    "message": f"余额仅剩 ¥{current_balance:.2f}，强制降级到本地模型",
                    "action": "force_degrade",
                })
            elif current_balance <= BALANCE_LOW_THRESHOLD:
                level = "warning"
                alerts.append({
                    "type": "balance_low",
                    "message": f"余额 ¥{current_balance:.2f} < ¥{BALANCE_LOW_THRESHOLD}，建议降级",
                    "action": "suggest_degrade",
                })
        
        # 日预算检查
        if today_summary["total_cost_rmb"] > DAILY_BUDGET_CNY * 1.5:
            level = "warning"
            alerts.append({
                "type": "daily_budget_exceeded",
                "message": f"今日消耗 ¥{today_summary['total_cost_rmb']:.2f} 超过日预算 ¥{DAILY_BUDGET_CNY:.2f} 的 150%",
                "action": "throttle",
            })
        
        return {
            "level": level,
            "alerts": alerts,
            "today": today_summary,
        }
    
    def get_recommended_model(self, current_balance: float = None) -> str:
        """根据余额推荐模型"""
        if current_balance is not None and current_balance <= BALANCE_CRITICAL_THRESHOLD:
            return "local-coder"
        if current_balance is not None and current_balance <= BALANCE_LOW_THRESHOLD:
            return "deepseek-v4-flash"  # 便宜
        return "minimax-m3"  # 默认
    
    def get_status(self) -> Dict:
        """综合状态"""
        return {
            "today": self.get_today_summary(),
            "week": self.get_week_summary(),
            "pricing": PRICING,
            "db_path": str(self.db_path),
        }
    
    def export_daily_to_json(self, days: int = 30) -> str:
        """导出最近 N 天数据为 JSON"""
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = self.conn.execute(
            "SELECT timestamp, model, input_tokens, output_tokens, cost_rmb FROM usage_log WHERE date(timestamp) >= ? ORDER BY timestamp",
            (cutoff,),
        ).fetchall()
        
        data = [
            {"ts": r[0], "model": r[1], "in": r[2], "out": r[3], "cost": round(r[4], 6)}
            for r in rows
        ]
        return json.dumps(data, ensure_ascii=False)
    
    def close(self):
        self.conn.close()


# ── 一键监控函数（供 cron 调用） ──

def quick_token_report() -> str:
    """快速生成报告"""
    tm = TokenMonitor()
    status = tm.get_status()
    today = status["today"]
    
    lines = [
        f"## Token 用量报告 {today['date']}",
        f"",
        f"| 指标 | 数值 |",
        f"|------|------|",
        f"| 今日消耗 | ¥{today['total_cost_rmb']:.4f} |",
        f"| 输入 tokens | {today['total_input_tokens']:,} |",
        f"| 输出 tokens | {today['total_output_tokens']:,} |",
        f"| API 调用次数 | {today['total_api_calls']} |",
        f"| 日预算 | ¥{today['daily_budget_rmb']:.2f} |",
        f"| 剩余预算 | ¥{today['remaining_budget_rmb']:.2f} |",
        f"| 预算使用率 | {today['budget_pct_used']}% |",
        f"",
    ]
    
    if today["by_model"]:
        lines.append("### 按模型明细")
        lines.append("| 模型 | 输入 | 输出 | 费用 | 调用 |")
        lines.append("|------|------|------|------|------|")
        for model, m in today["by_model"].items():
            name = PRICING.get(model, {}).get("name", model)
            lines.append(f"| {name} | {m['input_tokens']:,} | {m['output_tokens']:,} | ¥{m['cost_rmb']:.4f} | {m['api_calls']} |")
    
    tm.close()
    return "\n".join(lines)


# ── 自测 ──

if __name__ == "__main__":
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Path(tmpdir) / "test_token.db"
        tm = TokenMonitor(str(db))
        
        # 模拟 API 调用
        tm.log_usage("minimax-m3", input_tokens=5000, output_tokens=2000, session_id="test")
        tm.log_usage("deepseek-v4-pro", input_tokens=10000, output_tokens=3000, session_id="test")
        tm.log_usage("minimax-m3", input_tokens=8000, output_tokens=1500, session_id="test")
        
        status = tm.get_status()
        today = status["today"]
        
        print(f"=== Token Monitor 自测 ===")
        print(f"今日消耗: ¥{today['total_cost_rmb']:.4f}")
        print(f"模型: {json.dumps(today['by_model'], ensure_ascii=False, indent=2)}")
        
        # 余额告警测试
        result = tm.check_balance(current_balance=3.0)
        print(f"\n余额 ¥3.0 告警: level={result['level']}, alerts={len(result['alerts'])}")
        for a in result["alerts"]:
            print(f"  [{a['type']}] {a['message']}")
        
        tm.close()
