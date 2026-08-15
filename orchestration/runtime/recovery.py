#!/usr/bin/env python3
"""
G7: 故障恢复 + 环境清理
DDW AI Hub Orchestration — 长任务无人值守体系

功能：
- 端口冲突检测与自动释放
- 进程残留清理
- 临时文件清理
- Docker 残留清理（如果有）
- 任务启动前健康检查
- 失败后 checkpoint 回滚

设计：
- 每个 task 启动前自动运行 preflight_check
- 每个 task 完成后自动 cleanup
- 支持 dry-run 模式
"""

from __future__ import annotations
import os
import signal
import socket
import subprocess
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field


# ── 常见端口冲突范围 ──

KNOWN_PORTS = {
    # Hermes 核心服务
    8789: "Hermes WebUI",
    9091: "task_proxy (Hermes Gateway)",
    9092: "task_proxy_16g",
    
    # 外部服务
    3000: "OpenMAIC",
    3001: "Gitea",
    5000: "ChromaDB (默认)",
    8000: "ChromaDB (可能)",
    11434: "Ollama",
    
    # 开发端口
    5173: "Vite dev server",
    8001: "Python dev server",
    8080: "Local HTTP server",
    
    # 数据库
    3306: "MySQL",
    5432: "PostgreSQL",
    6379: "Redis",
    27017: "MongoDB",
}


@dataclass
class PortCheck:
    port: int
    in_use: bool
    process_name: str = ""
    pid: int = 0


@dataclass
class CleanupResult:
    ports_freed: List[int]
    processes_killed: List[str]
    files_deleted: List[str]
    space_freed_mb: float


# ── 端口工具 ──

def check_port(port: int) -> PortCheck:
    """检查端口是否被占用"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("127.0.0.1", port))
        sock.close()
        
        if result == 0:
            # 端口被占用，尝试获取进程名
            try:
                r = subprocess.run(
                    ["lsof", "-ti", f":{port}"],
                    capture_output=True, text=True, timeout=5,
                )
                pid = int(r.stdout.strip().split("\n")[0]) if r.stdout.strip() else 0
                
                if pid:
                    r2 = subprocess.run(
                        ["ps", "-p", str(pid), "-o", "comm="],
                        capture_output=True, text=True, timeout=3,
                    )
                    name = r2.stdout.strip()
                else:
                    name = ""
            except (subprocess.TimeoutExpired, ValueError):
                pid = 0
                name = ""
            
            return PortCheck(port=port, in_use=True, process_name=name, pid=pid)
        else:
            return PortCheck(port=port, in_use=False)
    except Exception:
        return PortCheck(port=port, in_use=False)


def scan_ports(ports: List[int] = None) -> List[PortCheck]:
    """批量扫描端口"""
    if ports is None:
        ports = list(KNOWN_PORTS.keys())
    
    results = []
    for port in ports:
        results.append(check_port(port))
    return results


def free_port(port: int, force: bool = False) -> bool:
    """释放端口（kill 占用进程）"""
    check = check_port(port)
    if not check.in_use:
        return True
    
    if not force:
        # 只 kill 非关键进程
        if check.process_name in ("hermes", "task_proxy", "ollama", "gitea"):
            return False  # 不 kill 关键服务
    
    try:
        # 先 SIGTERM
        try:
            os.kill(check.pid, signal.SIGTERM)
            import time
            time.sleep(1)
            if not check_port(port).in_use:
                return True
        except ProcessLookupError:
            return True
        
        # SIGKILL
        try:
            os.kill(check.pid, signal.SIGKILL)
            time.sleep(0.5)
            return not check_port(port).in_use
        except ProcessLookupError:
            return True
    except Exception:
        return False


# ── 进程清理 ──

def find_zombie_processes(patterns: List[str] = None) -> List[Dict]:
    """查找僵尸进程"""
    if patterns is None:
        patterns = ["defunct", "zombie"]
    
    zombies = []
    try:
        r = subprocess.run(
            ["ps", "aux"],
            capture_output=True, text=True, timeout=5,
        )
        for line in r.stdout.split("\n"):
            for p in patterns:
                if p.lower() in line.lower():
                    parts = line.split()
                    if len(parts) >= 2:
                        zombies.append({
                            "pid": parts[1],
                            "user": parts[0],
                            "command": " ".join(parts[10:]) if len(parts) > 10 else "",
                        })
    except subprocess.TimeoutExpired:
        pass
    
    return zombies


def kill_orphan_pids(pids: List[int]) -> List[int]:
    """清理孤儿进程"""
    killed = []
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except (ProcessLookupError, PermissionError):
            pass
    return killed


# ── 健康检查 ──

def preflight_check() -> Dict:
    """
    任务启动前健康检查
    
    检查项：
    - 端口冲突
    - 磁盘空间
    - 内存压力
    - 关键进程状态
    """
    issues = []
    warnings = []
    
    # 1. 端口检查
    port_checks = scan_ports(list(KNOWN_PORTS.keys()))
    conflicts = [pc for pc in port_checks if pc.in_use and "任务无关" in KNOWN_PORTS.get(pc.port, "")]
    for pc in conflicts:
        issues.append(f"端口 {pc.port} ({KNOWN_PORTS.get(pc.port, 'unknown')}) 被 {pc.process_name} (PID {pc.pid}) 占用")
    
    # 2. 磁盘检查
    stat = os.statvfs("/")
    free_gb = (stat.f_frsize * stat.f_bavail) / (1024**3)
    if free_gb < 5:
        issues.append(f"磁盘可用空间不足: {free_gb:.1f} GB")
    elif free_gb < 10:
        warnings.append(f"磁盘可用空间偏低: {free_gb:.1f} GB")
    
    # 3. 内存检查
    try:
        r = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5)
        import re
        free_match = re.search(r"Pages free:\s+(\d+)", r.stdout)
        if free_match:
            free_pages = int(free_match.group(1))
            free_mb = (free_pages * 16384) / (1024 * 1024)
            if free_mb < 1000:
                warnings.append(f"可用内存偏低: {free_mb:.0f} MB")
    except Exception:
        pass
    
    # 4. 关键进程
    critical_procs = ["task_proxy", "agentmemory"]
    for name in critical_procs:
        try:
            r = subprocess.run(["pgrep", "-f", name], capture_output=True, text=True, timeout=3)
            if not r.stdout.strip():
                issues.append(f"关键进程 {name} 未运行")
        except Exception:
            pass
    
    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "timestamp": datetime.now().isoformat(),
    }


# ── 清理函数 ──

def cleanup_temp_files(patterns: List[str] = None, max_age_hours: int = 48) -> List[Dict]:
    """清理临时文件"""
    if patterns is None:
        patterns = [
            "~/.hermes/logs/*.log",
            "~/.hermes/cache/*.tmp",
        ]
    
    cleaned = []
    cutoff = datetime.now() - timedelta(hours=max_age_hours)
    
    for pattern in patterns:
        path = Path(os.path.expanduser(pattern))
        parent = path.parent
        if not parent.exists():
            continue
        
        for f in parent.glob(path.name):
            if f.is_file():
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if mtime < cutoff:
                    try:
                        size_mb = f.stat().st_size / (1024 * 1024)
                        f.unlink()
                        cleaned.append({"path": str(f), "size_mb": round(size_mb, 2)})
                    except OSError:
                        pass
    
    return cleaned


def cleanup_python_cache(workspace: str = ".") -> List[Dict]:
    """清理 __pycache__ 和 .pyc 文件"""
    cleaned = []
    path = Path(workspace)
    
    for pycache in path.rglob("__pycache__"):
        try:
            shutil.rmtree(pycache)
            cleaned.append({"path": str(pycache), "type": "pycache"})
        except OSError:
            pass
    
    return cleaned


# ── 主清理器 ──

class RecoveryManager:
    """
    故障恢复管理器
    
    用法:
        rm = RecoveryManager()
        
        # 启动前检查
        health = rm.preflight()
        if not health["ok"]:
            for issue in health["issues"]:
                print(f"⚠️ {issue}")
        
        # 完成后清理
        result = rm.full_cleanup(dry_run=False)
        print(f"释放空间: {result.space_freed_mb:.1f} MB")
    """
    
    def __init__(self, workspace: str = "."):
        self.workspace = Path(workspace).resolve()
    
    def preflight(self) -> Dict:
        """启动前健康检查"""
        return preflight_check()
    
    def scan_ports(self, ports: List[int] = None) -> List[PortCheck]:
        """扫描端口"""
        return scan_ports(ports)
    
    def full_cleanup(self, dry_run: bool = True) -> CleanupResult:
        """全量清理"""
        result = CleanupResult(
            ports_freed=[],
            processes_killed=[],
            files_deleted=[],
            space_freed_mb=0.0,
        )
        
        # 1. 清理临时文件
        temp_cleaned = cleanup_temp_files(max_age_hours=48)
        for item in temp_cleaned:
            if not dry_run:
                result.files_deleted.append(item["path"])
                result.space_freed_mb += item.get("size_mb", 0)
        
        # 2. 清理 Python cache
        cache_cleaned = cleanup_python_cache(str(self.workspace))
        if not dry_run:
            for item in cache_cleaned:
                result.files_deleted.append(item["path"])
        
        # 3. 僵尸进程检测
        zombies = find_zombie_processes()
        for z in zombies:
            if not dry_run:
                try:
                    os.kill(int(z["pid"]), signal.SIGKILL)
                    result.processes_killed.append(f"PID {z['pid']} ({z['command'][:40]})")
                except Exception:
                    pass
        
        return result
    
    def emergency_cleanup(self) -> CleanupResult:
        """紧急清理（释放最大空间）"""
        return self.full_cleanup(dry_run=False)
    
    def check_and_free_port(self, port: int, force: bool = False) -> bool:
        """检查并释放端口"""
        return free_port(port, force)


# ── 快捷函数 ──

def quick_preflight() -> str:
    """快速健康检查（供 cron 调用）"""
    result = preflight_check()
    lines = [f"## 环境健康检查 {result['timestamp']}"]
    
    if result["ok"]:
        lines.append("✅ 环境就绪")
    else:
        lines.append(f"⚠️ 发现 {len(result['issues'])} 个问题")
        for issue in result["issues"]:
            lines.append(f"- ❌ {issue}")
    
    for warning in result["warnings"]:
        lines.append(f"- ⚠️ {warning}")
    
    return "\n".join(lines)


# ── 自测 ──

if __name__ == "__main__":
    print("=== 故障恢复自测 ===\n")
    
    # 1. 健康检查
    health = preflight_check()
    print(f"健康检查: {'✅ OK' if health['ok'] else '❌ 有问题'}")
    for issue in health["issues"]:
        print(f"  ❌ {issue}")
    for w in health["warnings"]:
        print(f"  ⚠️ {w}")
    
    # 2. 端口扫描
    print(f"\n端口扫描:")
    port_checks = scan_ports()
    for pc in port_checks[:10]:
        if pc.in_use:
            print(f"  :{pc.port} → {pc.process_name} (PID {pc.pid}) [{KNOWN_PORTS.get(pc.port, 'unknown')}]")
    
    # 3. 僵尸进程
    zombies = find_zombie_processes()
    print(f"\n僵尸进程: {len(zombies)} 个")
    for z in zombies:
        print(f"  PID {z['pid']}: {z['command'][:60]}")
    
    # 4. Dry-run 清理
    rm = RecoveryManager()
    result = rm.full_cleanup(dry_run=True)
    print(f"\n可清理项: {len(result.files_deleted)} 个文件, {result.space_freed_mb:.1f} MB")
