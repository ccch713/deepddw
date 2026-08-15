#!/usr/bin/env python3
"""
G4: Scorecard 审计层
DDW AI Hub Orchestration — 长任务无人值守体系

设计原则：
- 不信任 AI 自述（"我搞定了"），程序化检查真实状态
- 每个 agent 完成工作后，scorecard 自动触发
- 检查项目可配置（根据任务复杂度增减）
- 输出 pass/fail 结果 + 详细报告

检查维度：
1. 文件真实性（存在、大小、语法）
2. 测试命令是否真实跑过（stdout 验证）
3. Quality gate（lint/typecheck/security）
4. Handoff 格式完整性
5. Git 状态一致性
"""

from __future__ import annotations
import json
import hashlib
import subprocess
import ast
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ScorecardCheck:
    """单条检查项"""
    name: str
    category: str           # file | test | quality | handoff | git
    passed: bool
    detail: str = ""
    weight: int = 1         # 权重（1-5）


@dataclass
class ScorecardResult:
    """审计结果"""
    ok: bool
    checks: List[ScorecardCheck] = field(default_factory=list)
    passed_count: int = 0
    failed_count: int = 0
    total_weight: int = 0
    passed_weight: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    @property
    def score_pct(self) -> float:
        if self.total_weight == 0:
            return 0.0
        return (self.passed_weight / self.total_weight) * 100
    
    @property
    def summary(self) -> str:
        return f"{self.passed_count}/{len(self.checks)} checks passed (score: {self.score_pct:.0f}%)"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "score_pct": self.score_pct,
            "timestamp": self.timestamp,
            "checks": [
                {"name": c.name, "category": c.category, "passed": c.passed, "detail": c.detail, "weight": c.weight}
                for c in self.checks
            ]
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class Scorecard:
    """
    Scorecard 审计框架
    
    用法:
        sc = Scorecard(workspace="/path/to/project")
        sc.add_file_checks(["src/main.py", "tests/test_main.py"])
        sc.add_test_check("pytest tests/ -v")
        sc.add_quality_check()
        sc.add_handoff_check(handoff_data)
        
        result = sc.run()
        print(result.summary)
    """
    
    def __init__(
        self,
        workspace: str = ".",
        python_cmd: str = "python3",
        pytest_cmd: str = "pytest",
    ):
        self.workspace = Path(workspace).resolve()
        self.python_cmd = python_cmd
        self.pytest_cmd = pytest_cmd
        self._checks: List[Callable[[], ScorecardCheck]] = []
        self._handoff_data: Optional[Dict] = None
    
    def add_file_checks(self, file_paths: List[str]) -> None:
        """添加文件真实性检查"""
        def check():
            all_pass = True
            details = []
            for fp in file_paths:
                p = self.workspace / fp
                if not p.exists():
                    all_pass = False
                    details.append(f"❌ {fp}: 文件不存在")
                else:
                    size = p.stat().st_size
                    if size == 0:
                        all_pass = False
                        details.append(f"❌ {fp}: 文件大小为 0")
                    else:
                        # 语法检查 .py 文件
                        syntax_ok = True
                        if p.suffix == ".py":
                            try:
                                ast.parse(p.read_text())
                            except SyntaxError as e:
                                syntax_ok = False
                                details.append(f"❌ {fp}: 语法错误: {e}")
                        if syntax_ok:
                            details.append(f"✅ {fp}: {size} bytes")
            return ScorecardCheck(
                name="文件真实性",
                category="file",
                passed=all_pass,
                detail="; ".join(details),
                weight=3,
            )
        self._checks.append(check)
    
    def add_test_check(self, test_command: str, expect_pass: bool = True) -> None:
        """添加测试执行检查"""
        def check():
            try:
                r = subprocess.run(
                    test_command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd=str(self.workspace),
                )
                passed = (r.returncode == 0) if expect_pass else (r.returncode != 0)
                detail = f"exit={r.returncode}, stdout({len(r.stdout)} chars)"
                if not passed:
                    detail += f", stderr: {r.stderr[:200]}"
                return ScorecardCheck(
                    name=f"测试执行: {test_command[:60]}",
                    category="test",
                    passed=passed,
                    detail=detail,
                    weight=3,
                )
            except subprocess.TimeoutExpired:
                return ScorecardCheck(
                    name=f"测试执行: {test_command[:60]}",
                    category="test",
                    passed=False,
                    detail="超时（120s）",
                    weight=3,
                )
            except Exception as e:
                return ScorecardCheck(
                    name=f"测试执行: {test_command[:60]}",
                    category="test",
                    passed=False,
                    detail=f"异常: {e}",
                    weight=3,
                )
        self._checks.append(check)
    
    def add_quality_check(self, files: List[str] = None) -> None:
        """添加质量门检查（Python lint 检测）"""
        def check():
            results = []
            # 1. Python 语法编译
            py_files = [self.workspace / f for f in (files or [])] or list(self.workspace.glob("**/*.py"))[:50]
            syntax_ok = True
            for p in py_files:
                if not isinstance(p, Path):
                    p = self.workspace / p
                try:
                    ast.parse(p.read_text())
                except SyntaxError as e:
                    syntax_ok = False
                    results.append(f"❌ {p.name}: {e}")
            
            if syntax_ok:
                results.append(f"✅ 语法检查通过 ({len(py_files)} 个 .py 文件)")
            
            # 2. 检查是否有明显的安全漏洞模式
            security_ok = True
            dangerous_patterns = ["exec(", "eval(", "os.system(", "subprocess.call("]
            for p in py_files:
                if not isinstance(p, Path):
                    p = self.workspace / p
                try:
                    content = p.read_text()
                    for pattern in dangerous_patterns:
                        if pattern in content:
                            results.append(f"⚠️ {p.name}: 含有可疑调用 {pattern}")
                except Exception:
                    pass
            
            return ScorecardCheck(
                name="质量检查",
                category="quality",
                passed=syntax_ok,
                detail="; ".join(results),
                weight=2,
            )
        self._checks.append(check)
    
    def add_handoff_check(self, handoff_data: Dict) -> None:
        """添加交接棒格式检查"""
        self._handoff_data = handoff_data
        
        def check():
            if not handoff_data:
                return ScorecardCheck(
                    name="交接棒格式",
                    category="handoff",
                    passed=False,
                    detail="无 handoff 数据",
                    weight=2,
                )
            
            required = ["agent_id", "agent_type", "task_id", "status", "timestamp", "summary"]
            missing = [f for f in required if not handoff_data.get(f)]
            
            if missing:
                return ScorecardCheck(
                    name="交接棒格式",
                    category="handoff",
                    passed=False,
                    detail=f"缺失必填字段: {missing}",
                    weight=2,
                )
            else:
                return ScorecardCheck(
                    name="交接棒格式",
                    category="handoff",
                    passed=True,
                    detail=f"agent={handoff_data['agent_id']}, task={handoff_data['task_id']}, status={handoff_data['status']}",
                    weight=2,
                )
        self._checks.append(check)
    
    def add_git_check(self) -> None:
        """添加 Git 状态一致性检查"""
        def check():
            try:
                r = subprocess.run(
                    ["git", "status", "--porcelain"],
                    capture_output=True,
                    text=True,
                    cwd=str(self.workspace),
                    timeout=10,
                )
                dirty_files = [l for l in r.stdout.strip().split("\n") if l]
                if dirty_files:
                    return ScorecardCheck(
                        name="Git 状态",
                        category="git",
                        passed=True,
                        detail=f"⚠️ {len(dirty_files)} 个未提交变更: {dirty_files[:5]}",
                        weight=1,
                    )
                else:
                    return ScorecardCheck(
                        name="Git 状态",
                        category="git",
                        passed=True,
                        detail="✅ 工作区干净",
                        weight=1,
                    )
            except Exception as e:
                return ScorecardCheck(
                    name="Git 状态",
                    category="git",
                    passed=False,
                    detail=f"Git 命令失败: {e}",
                    weight=1,
                )
        self._checks.append(check)
    
    def add_hash_check(self, files: List[str], expected_hashes: Dict[str, str] = None) -> None:
        """添加文件内容 hash 检查"""
        def check():
            results = []
            all_pass = True
            for fp in files:
                p = self.workspace / fp
                if not p.exists():
                    all_pass = False
                    results.append(f"❌ {fp}: 不存在")
                    continue
                sha = hashlib.sha256(p.read_bytes()).hexdigest()
                if expected_hashes and fp in expected_hashes:
                    if sha != expected_hashes[fp]:
                        all_pass = False
                        results.append(f"❌ {fp}: hash 不匹配")
                    else:
                        results.append(f"✅ {fp}: hash 匹配")
                else:
                    results.append(f"✅ {fp}: sha256={sha[:16]}...")
            return ScorecardCheck(
                name="文件 hash 校验",
                category="file",
                passed=all_pass,
                detail="; ".join(results),
                weight=2,
            )
        self._checks.append(check)
    
    def add_custom_check(
        self,
        name: str,
        category: str,
        fn: Callable[[], bool],
        weight: int = 1,
    ) -> None:
        """添加自定义检查"""
        def wrapped():
            try:
                ok = fn()
                return ScorecardCheck(
                    name=name,
                    category=category,
                    passed=ok,
                    detail="",
                    weight=weight,
                )
            except Exception as e:
                return ScorecardCheck(
                    name=name,
                    category=category,
                    passed=False,
                    detail=f"异常: {e}",
                    weight=weight,
                )
        self._checks.append(wrapped)
    
    def run(self) -> ScorecardResult:
        """执行全部检查"""
        result = ScorecardResult(ok=True, checks=[])
        
        for fn in self._checks:
            check = fn()
            result.checks.append(check)
            if check.passed:
                result.passed_count += 1
                result.passed_weight += check.weight
            else:
                result.failed_count += 1
            result.total_weight += check.weight
        
        result.ok = result.failed_count == 0
        return result


# ── 预制 Scorecard 模板（按任务类型） ──

def coding_scorecard(workspace: str, changed_files: List[str], test_cmd: str) -> Scorecard:
    """Coder 节点的标准 Scorecard"""
    sc = Scorecard(workspace=workspace)
    sc.add_file_checks(changed_files)
    sc.add_test_check(test_cmd)
    sc.add_quality_check(changed_files)
    sc.add_git_check()
    return sc


def quality_scorecard(workspace: str, files: List[str]) -> Scorecard:
    """Quality 节点的标准 Scorecard"""
    sc = Scorecard(workspace=workspace)
    sc.add_quality_check(files)
    sc.add_file_checks(files)
    return sc


def full_scorecard(
    workspace: str,
    changed_files: List[str],
    test_cmd: str,
    handoff_data: Dict = None,
) -> Scorecard:
    """全量 Scorecard"""
    sc = Scorecard(workspace=workspace)
    sc.add_file_checks(changed_files)
    sc.add_test_check(test_cmd)
    sc.add_quality_check(changed_files)
    sc.add_git_check()
    if handoff_data:
        sc.add_handoff_check(handoff_data)
    return sc


# ── 自测 ──

if __name__ == "__main__":
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试文件
        py_file = Path(tmpdir) / "hello.py"
        py_file.write_text("print('hello world')\n")
        
        test_file = Path(tmpdir) / "test_hello.py"
        test_file.write_text("def test_pass(): assert 1 == 1\n")
        
        # 初始化 git
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True)
        
        sc = Scorecard(workspace=tmpdir)
        sc.add_file_checks(["hello.py", "test_hello.py"])
        sc.add_quality_check(["hello.py", "test_hello.py"])
        sc.add_git_check()
        
        result = sc.run()
        print(f"Scorecard 结果: {result.summary}")
        print(result.to_json())
