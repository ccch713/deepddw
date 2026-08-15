#!/usr/bin/env python3
"""
P4: 磁盘水位监控
DDW AI Hub Orchestration — 长任务无人值守体系

功能：
- 监控磁盘使用率
- 水位告警（>80% warn, >90% critical, >95% emergency）
- 自动清理：旧日志 / 临时文件 / Docker 残留
- 大文件/目录发现
- 可配置清理策略

设计：
- 独立进程，可 cron 定时调用
- 支持自定义清理规则
- dry-run 模式（先看会删什么）
"""

from __future__ import annotations
import os
import shutil
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


# ── 默认配置 ──

DEFAULT_CONFIG = {
    "watermark_warn": 80.0,        # 警告水位 (%)
    "watermark_critical": 90.0,    # 严重水位
    "watermark_emergency": 95.0,   # 紧急水位
    
    "cleanup_paths": {
        "tmp_old": {
            "path": "/tmp",
            "max_age_hours": 48,
            "pattern": "hermes-*",
            "enabled": True,
        },
        "logs_old": {
            "path": "~/.hermes/logs",
            "max_age_days": 7,
            "pattern": "*.log",
            "enabled": True,
        },
        "brew_cache": {
            "path": "~/Library/Caches/Homebrew",
            "max_size_mb": 2048,
            "enabled": False,  # 手动控制
        },
        "pip_cache": {
            "path": "~/Library/Caches/pip",
            "max_size_mb": 1024,
            "enabled": False,
        },
    },
    
    "large_file_threshold_mb": 500,   # 大于此值标记为大文件
    "scan_paths": ["/", "~/workspace", "~/.hermes"],
}


# ── 工具函数 ──

def get_size_mb(path: Path) -> float:
    """获取文件/目录大小（MB）"""
    try:
        if path.is_file():
            return path.stat().st_size / (1024 * 1024)
        elif path.is_dir():
            total = 0
            for f in path.rglob("*"):
                if f.is_file():
                    try:
                        total += f.stat().st_size
                    except OSError:
                        pass
            return total / (1024 * 1024)
    except OSError:
        return 0.0
    return 0.0


def get_largest_files(directory: str, top_n: int = 20) -> List[Dict]:
    """发现大文件"""
    path = Path(os.path.expanduser(directory))
    if not path.exists():
        return []
    
    files = []
    try:
        for f in path.rglob("*"):
            if f.is_file():
                try:
                    size_mb = f.stat().st_size / (1024 * 1024)
                    if size_mb > 10:  # 只统计 > 10MB
                        files.append({
                            "path": str(f),
                            "size_mb": round(size_mb, 1),
                            "age_days": round((datetime.now() - datetime.fromtimestamp(f.stat().st_mtime)).total_seconds() / 86400, 1),
                        })
                except OSError:
                    pass
    except PermissionError:
        pass
    
    files.sort(key=lambda x: x["size_mb"], reverse=True)
    return files[:top_n]


def cleanup_old_files(
    directory: str,
    pattern: str,
    max_age_hours: int = None,
    max_age_days: int = None,
    max_size_mb: float = None,
    dry_run: bool = True,
) -> List[Dict]:
    """清理旧文件，返回清理清单"""
    path = Path(os.path.expanduser(directory))
    if not path.exists():
        return []
    
    deleted = []
    
    if max_age_hours:
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        for f in path.glob(pattern):
            if f.is_file():
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if mtime < cutoff:
                    deleted.append({"path": str(f), "reason": f"age > {max_age_hours}h", "size_mb": round(f.stat().st_size / (1024*1024), 2)})
                    if not dry_run:
                        try:
                            f.unlink()
                        except OSError:
                            pass
    
    if max_age_days:
        cutoff = datetime.now() - timedelta(days=max_age_days)
        for f in path.glob(pattern):
            if f.is_file():
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if mtime < cutoff:
                    deleted.append({"path": str(f), "reason": f"age > {max_age_days}d", "size_mb": round(f.stat().st_size / (1024*1024), 2)})
                    if not dry_run:
                        try:
                            f.unlink()
                        except OSError:
                            pass
    
    return deleted


# ── 磁盘监控 ──

@dataclass
class DiskStatus:
    mount: str
    total_gb: float
    used_gb: float
    free_gb: float
    pct_used: float
    
    @property
    def level(self) -> str:
        if self.pct_used >= 95:
            return "emergency"
        elif self.pct_used >= 90:
            return "critical"
        elif self.pct_used >= 80:
            return "warning"
        return "ok"


class DiskMonitor:
    """
    磁盘水位监控
    
    用法:
        dm = DiskMonitor()
        status = dm.check()
        print(f"磁盘 {status.pct_used:.0f}% 使用, 等级: {status.level}")
        
        # 自动清理
        if status.level in ("warning", "critical", "emergency"):
            cleaned = dm.auto_cleanup(dry_run=False)
            print(f"清理了 {len(cleaned)} 个文件")
    """
    
    def __init__(self, config: Dict = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
    
    def check(self) -> DiskStatus:
        """检查磁盘状态"""
        stat = os.statvfs("/")
        total = (stat.f_frsize * stat.f_blocks) / (1024**3)
        free = (stat.f_frsize * stat.f_bavail) / (1024**3)
        used = total - free
        pct = round((used / total) * 100, 1) if total > 0 else 0
        
        return DiskStatus(
            mount="/",
            total_gb=round(total, 1),
            used_gb=round(used, 1),
            free_gb=round(free, 1),
            pct_used=pct,
        )
    
    def auto_cleanup(self, dry_run: bool = True) -> List[Dict]:
        """自动清理"""
        cleaned = []
        
        for name, cfg in self.config.get("cleanup_paths", {}).items():
            if not cfg.get("enabled", False):
                continue
            
            path = os.path.expanduser(cfg["path"])
            pattern = cfg.get("pattern", "*")
            max_age_h = cfg.get("max_age_hours")
            max_age_d = cfg.get("max_age_days")
            max_size = cfg.get("max_size_mb")
            
            if max_age_h or max_age_d:
                items = cleanup_old_files(path, pattern, max_age_h, max_age_d, dry_run=dry_run)
                cleaned.extend(items)
        
        return cleaned
    
    def get_large_items(self, top_n: int = 10) -> Dict[str, List[Dict]]:
        """发现大文件和目录"""
        result = {}
        for scan_path in self.config.get("scan_paths", []):
            path = os.path.expanduser(scan_path)
            if Path(path).exists():
                result[scan_path] = get_largest_files(path, top_n)
        return result
    
    def generate_report(self) -> str:
        """生成完整报告"""
        status = self.check()
        large_items = self.get_large_items()
        
        lines = [
            f"## 磁盘监控报告 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| 挂载点 | {status.mount} |",
            f"| 总容量 | {status.total_gb:.1f} GB |",
            f"| 已使用 | {status.used_gb:.1f} GB ({status.pct_used:.1f}%) |",
            f"| 可用 | {status.free_gb:.1f} GB |",
            f"| 水位等级 | **{status.level.upper()}** |",
            "",
        ]
        
        # 告警建议
        if status.level != "ok":
            lines.append("### ⚠️ 建议清理")
            dry_run = self.auto_cleanup(dry_run=True)
            if dry_run:
                total_mb = sum(item.get("size_mb", 0) for item in dry_run)
                lines.append(f"- 可清理 {len(dry_run)} 个文件，释放约 {total_mb:.1f} MB")
                for item in dry_run[:5]:
                    lines.append(f"  - `{item['path']}` ({item['size_mb']:.1f} MB, {item['reason']})")
                if len(dry_run) > 5:
                    lines.append(f"  - ... 还有 {len(dry_run) - 5} 个")
        
        # 大文件
        if large_items:
            lines.append("")
            lines.append("### 📁 大文件 (>10MB)")
            for scan_path, items in large_items.items():
                if items:
                    lines.append(f"\n**{scan_path}**")
                    lines.append("| 文件 | 大小 | 天数 |")
                    lines.append("|------|------|------|")
                    for item in items[:10]:
                        lines.append(f"| `{item['path']}` | {item['size_mb']:.0f} MB | {item['age_days']:.0f}d |")
        
        return "\n".join(lines)


# ── 方便函数 ──

def quick_disk_check() -> str:
    """快速检查磁盘（供 cron 使用）"""
    dm = DiskMonitor()
    return dm.generate_report()


# ── 自测 ──

if __name__ == "__main__":
    dm = DiskMonitor()
    status = dm.check()
    
    print(f"=== 磁盘监控自测 ===")
    print(f"总量: {status.total_gb:.1f} GB")
    print(f"已用: {status.used_gb:.1f} GB ({status.pct_used:.1f}%)")
    print(f"可用: {status.free_gb:.1f} GB")
    print(f"水位: {status.level}")
    
    # 大文件
    top = get_largest_files(os.path.expanduser("~/workspace"), 5)
    print(f"\n~/workspace 大文件 TOP 5:")
    for f in top:
        print(f"  {f['size_mb']:.0f} MB  {f['path']}")
    
    # dry-run 清理
    cleaned = dm.auto_cleanup(dry_run=True)
    print(f"\n可清理 {len(cleaned)} 个文件:")
    for c in cleaned[:5]:
        print(f"  {c['path']} ({c['size_mb']} MB, {c['reason']})")
