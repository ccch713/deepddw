#!/usr/bin/env python3
"""
G2: 结构化交接棒校验器
DDW AI Hub Orchestration — 长任务无人值守体系

功能：
- 校验 handoff 数据是否包含所有必填字段
- 按 agent_type 区分必填要求
- 缺失字段 → 立即打回 + 错误信息
- 支持 JSON 字符串、dict、Handoff 对象三种输入
"""

from __future__ import annotations
import json
from typing import Dict, Any, List, Tuple, Union
from pathlib import Path

# 导入 schema
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from schemas.handoff_schema import (
    Handoff, HandoffStatus, get_required_fields, FIELD_DESCRIPTIONS
)


class HandoffValidationError(Exception):
    """交接棒校验失败"""
    def __init__(self, message: str, missing_fields: List[str]):
        super().__init__(message)
        self.missing_fields = missing_fields


class HandoffValidator:
    """
    交接棒校验器
    
    用法:
        validator = HandoffValidator()
        result = validator.validate(handoff_dict)
        if not result.ok:
            print(result.errors)
    """
    
    def validate(self, handoff: Union[Dict, str, Handoff]) -> "ValidationResult":
        """
        校验交接棒数据
        
        Returns:
            ValidationResult: ok=True 表示通过，ok=False 含 error 详情
        """
        # 解析输入
        if isinstance(handoff, str):
            try:
                data = json.loads(handoff)
            except json.JSONDecodeError as e:
                return ValidationResult(ok=False, errors=[f"JSON 解析失败: {e}"])
        elif isinstance(handoff, Handoff):
            data = handoff.to_dict()
        else:
            data = handoff
        
        errors = []
        warnings = []
        
        # 1. 检查通用必填字段
        common_required = ["agent_id", "agent_type", "task_id", "status", "timestamp", "summary"]
        for field in common_required:
            if not data.get(field):
                errors.append(f"缺失通用必填字段: {field} ({FIELD_DESCRIPTIONS.get(field, '')})")
        
        # 2. 检查 agent_type 合法性
        agent_type = data.get("agent_type", "")
        if agent_type and agent_type not in get_required_fields.__globals__["REQUIRED_FIELDS"]:
            valid_types = [k for k in get_required_fields.__globals__["REQUIRED_FIELDS"].keys() if k != "all"]
            warnings.append(f"未知 agent_type '{agent_type}'，合法值: {valid_types}")
        
        # 3. 检查 status 合法性
        status_val = data.get("status", "")
        valid_statuses = [s.value for s in HandoffStatus]
        if status_val and status_val not in valid_statuses:
            errors.append(f"无效 status '{status_val}'，合法值: {valid_statuses}")
        
        # 4. 按 agent_type 检查特殊必填字段
        if agent_type in get_required_fields.__globals__["REQUIRED_FIELDS"]:
            extra = get_required_fields.__globals__["REQUIRED_FIELDS"][agent_type]
            for field in extra:
                if field == "changed_files":
                    if not data.get("changed_files"):
                        errors.append(f"缺失必填字段: changed_files ({agent_type} 必须列出变更文件)")
                elif field == "test_results":
                    if not data.get("test_results"):
                        errors.append(f"缺失必填字段: test_results ({agent_type} 必须提供测试结果)")
                elif field == "quality_checks":
                    if not data.get("quality_checks"):
                        errors.append(f"缺失必填字段: quality_checks ({agent_type} 必须提供质量检查)")
                elif field == "pr_target":
                    if not data.get("pr_target"):
                        errors.append(f"缺失必填字段: pr_target ({agent_type} 必须提供 PR 目标分支)")
        
        # 5. changed_files 深度校验
        changed_files = data.get("changed_files", [])
        if isinstance(changed_files, list):
            for i, cf in enumerate(changed_files):
                if not isinstance(cf, dict):
                    errors.append(f"changed_files[{i}] 不是 dict 类型")
                    continue
                if not cf.get("path"):
                    errors.append(f"changed_files[{i}] 缺失 path 字段")
        
        # 6. test_results 深度校验
        test_results = data.get("test_results")
        if isinstance(test_results, dict):
            # exit_code 存在但非数值 → warning
            if "exit_code" in test_results and not isinstance(test_results["exit_code"], int):
                warnings.append(f"test_results.exit_code 应为 int，当前: {type(test_results['exit_code']).__name__}")
        
        return ValidationResult(
            ok=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            handoff=Handoff.from_dict(data) if errors == [] else None,
        )
    
    def validate_or_raise(self, handoff: Union[Dict, str, Handoff]) -> Handoff:
        """校验，不通过则抛异常"""
        result = self.validate(handoff)
        if not result.ok:
            raise HandoffValidationError(
                f"交接棒校验失败 ({len(result.errors)} 个错误): " + "; ".join(result.errors),
                result.errors
            )
        return result.handoff


class ValidationResult:
    """校验结果"""
    def __init__(
        self,
        ok: bool,
        errors: List[str] = None,
        warnings: List[str] = None,
        handoff: Handoff = None,
    ):
        self.ok = ok
        self.errors = errors or []
        self.warnings = warnings or []
        self.handoff = handoff
    
    def __repr__(self) -> str:
        status = "✅ PASS" if self.ok else f"❌ FAIL ({len(self.errors)} errors)"
        lines = [f"ValidationResult: {status}"]
        for e in self.errors:
            lines.append(f"  ❌ {e}")
        for w in self.warnings:
            lines.append(f"  ⚠️ {w}")
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
        }


# ── 便捷函数 ──

def validate_handoff(data: Union[Dict, str]) -> ValidationResult:
    """一键校验交接棒"""
    return HandoffValidator().validate(data)


# ── 自测 ──

if __name__ == "__main__":
    # 合法交接棒
    valid_handoff = {
        "agent_id": "coder-1",
        "agent_type": "coder",
        "task_id": "task-001",
        "status": "success",
        "timestamp": "2026-06-29T19:00:00+08:00",
        "summary": "完成 User 模型创建",
        "changed_files": [
            {"path": "src/models/user.py", "action": "create", "lines_added": 45, "lines_removed": 0, "size_bytes": 1234}
        ],
        "test_results": {
            "command": "pytest tests/models/test_user.py -v",
            "exit_code": 0,
            "total": 5,
            "passed": 5,
            "failed": 0,
            "output_excerpt": "5 passed in 0.5s"
        }
    }
    
    # 非法交接棒（缺字段）
    invalid_handoff = {
        "agent_id": "coder-2",
        "agent_type": "coder",
        # 缺 task_id, summary, changed_files, test_results
    }
    
    print("=== 合法交接棒 ===")
    r = validate_handoff(valid_handoff)
    print(r)
    print(f"handoff: {r.handoff.agent_id if r.handoff else 'None'}")
    
    print("\n=== 非法交接棒 ===")
    r = validate_handoff(invalid_handoff)
    print(r)
    
    # 验证抛异常
    print("\n=== 抛异常模式 ===")
    try:
        HandoffValidator().validate_or_raise(invalid_handoff)
    except HandoffValidationError as e:
        print(f"捕获异常: {e}")
        print(f"缺失字段: {e.missing_fields}")
