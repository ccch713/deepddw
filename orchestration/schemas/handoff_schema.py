#!/usr/bin/env python3
"""
G2: 结构化交接棒 Schema 定义
DDW AI Hub Orchestration — 长任务无人值守体系

设计原则：
- 每个 agent 完成任务后输出固定格式的 handoff YAML
- 缺失字段 = 系统当场打回，不信任 AI 的 "我搞定了"
- Schema 可扩展，按任务类型定义不同字段
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from enum import Enum
import json


class HandoffStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"
    BLOCKED = "blocked"


class HandoffOrigin(str, Enum):
    CODER = "coder"
    TESTER = "tester"
    REVIEWER = "reviewer"
    QUALITY = "quality"
    COMMITTER = "committer"
    RESEARCHER = "researcher"
    ANALYZER = "analyzer"
    CUSTOM = "custom"


@dataclass
class FileChange:
    """单个文件变更记录"""
    path: str                          # 绝对/相对路径
    action: str                        # create | modify | delete
    lines_added: int = 0
    lines_removed: int = 0
    size_bytes: int = 0


@dataclass
class TestResult:
    """测试执行结果"""
    command: str                       # 实际执行的测试命令
    exit_code: int                     # 0=pass
    total: int = 0
    passed: int = 0
    failed: int = 0
    coverage_pct: Optional[float] = None
    output_excerpt: str = ""           # 测试输出摘要（前 500 字符）
    artifacts: List[str] = field(default_factory=list)  # 测试产物路径


@dataclass
class QualityCheck:
    """代码质量检查"""
    lint: bool = False
    typecheck: bool = False
    security_scan: bool = False
    lint_output: str = ""
    typecheck_output: str = ""
    security_output: str = ""


@dataclass
class Handoff:
    """
    标准化交接棒数据
    
    每个 agent 节点完成任务后必须输出此结构。
    缺失必填字段 → handoff_validator 当场打回。
    """
    # ── 元信息 ──
    agent_id: str                      # 节点标识（必填）
    agent_type: str                    # coder/tester/reviewer/...（必填）
    task_id: str                       # 关联任务 ID（必填）
    status: HandoffStatus              # 完成状态（必填）
    timestamp: str                     # ISO 8601（必填）
    
    # ── 产出物 ──
    changed_files: List[FileChange] = field(default_factory=list)  # 变更文件列表
    output_files: List[str] = field(default_factory=list)          # 产出文件路径
    pr_target: Optional[str] = None    # PR 目标分支
    
    # ── 验证 ──
    test_results: Optional[TestResult] = None      # 测试结果（coder/tester 必填）
    quality_checks: Optional[QualityCheck] = None  # 质量检查（quality 必填）
    
    # ── 上下文 ──
    summary: str = ""                  # 一句话总结做了什么
    blockers: List[str] = field(default_factory=list)  # 阻塞项
    notes: str = ""                    # 备注/传递给下游的说明
    
    # ── 元数据（可选） ──
    model_used: str = ""               # 使用的 LLM 模型
    tokens_used: int = 0               # token 消耗
    duration_seconds: float = 0.0      # 耗时
    custom_fields: Dict[str, Any] = field(default_factory=dict)  # 扩展字段

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Handoff":
        return cls(
            agent_id=data.get("agent_id", ""),
            agent_type=data.get("agent_type", ""),
            task_id=data.get("task_id", ""),
            status=HandoffStatus(data.get("status", "failed")),
            timestamp=data.get("timestamp", ""),
            changed_files=[FileChange(**f) for f in data.get("changed_files", [])],
            output_files=data.get("output_files", []),
            pr_target=data.get("pr_target"),
            test_results=TestResult(**data["test_results"]) if data.get("test_results") else None,
            quality_checks=QualityCheck(**data["quality_checks"]) if data.get("quality_checks") else None,
            summary=data.get("summary", ""),
            blockers=data.get("blockers", []),
            notes=data.get("notes", ""),
            model_used=data.get("model_used", ""),
            tokens_used=data.get("tokens_used", 0),
            duration_seconds=data.get("duration_seconds", 0.0),
            custom_fields=data.get("custom_fields", {}),
        )


# ── 必填字段定义（按 agent_type 区分） ──

REQUIRED_FIELDS = {
    "all": [
        "agent_id", "agent_type", "task_id", "status", "timestamp", "summary"
    ],
    "coder": [
        "changed_files", "test_results",
    ],
    "tester": [
        "test_results",
    ],
    "quality": [
        "quality_checks",
    ],
    "reviewer": [
        "changed_files",
    ],
    "committer": [
        "changed_files", "pr_target",
    ],
}

def get_required_fields(agent_type: str) -> List[str]:
    """获取指定 agent 类型的所有必填字段"""
    fields = list(REQUIRED_FIELDS.get("all", []))
    fields.extend(REQUIRED_FIELDS.get(agent_type, []))
    return fields


# ── Handoff 字段映射（供 validator 使用） ──

FIELD_DESCRIPTIONS = {
    "agent_id": "节点标识（如 coder-1, tester-3）",
    "agent_type": "节点类型：coder/tester/reviewer/quality/committer",
    "task_id": "关联任务 ID",
    "status": "完成状态：success/failed/needs_review/blocked",
    "timestamp": "ISO 8601 时间戳",
    "summary": "一句话总结（≤200 字）",
    "changed_files": "变更文件列表 [{path, action, lines_added, lines_removed, size_bytes}]",
    "output_files": "产出文件绝对路径列表",
    "pr_target": "PR 目标分支（committer 必填）",
    "test_results": "测试结果 {command, exit_code, total, passed, failed, coverage_pct, output_excerpt}",
    "quality_checks": "质量检查 {lint, typecheck, security_scan, lint_output, typecheck_output, security_output}",
    "blockers": "阻塞项列表",
    "notes": "备注/传递给下游的说明",
}
