"""碳硅协作：输入/输出规范检查引擎。

功能：
- 解析 node 的 input_spec 并逐项执行 quality_checks
- 解析 flow 的 output_spec 并检查产出物完整性
- 生成结构化拒绝消息
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class CheckResult:
    check_type: str
    severity: str  # reject / reject_with_feedback / block / warn
    passed: bool
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SpecCheckReport:
    passed: bool
    results: List[CheckResult] = field(default_factory=list)
    blocking_failures: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "results": [
                {"check_type": r.check_type, "severity": r.severity,
                 "passed": r.passed, "message": r.message}
                for r in self.results
            ],
            "blocking_failures": self.blocking_failures,
        }


class InputSpecChecker:
    """检查输入数据是否符合 input_spec 规范。"""

    def check(self, input_spec: dict, actual_data: dict) -> SpecCheckReport:
        """执行输入规范检查。

        Args:
            input_spec: node 的 input_spec JSON
            actual_data: 实际输入数据

        Returns:
            SpecCheckReport: 检查报告
        """
        report = SpecCheckReport(passed=True)

        if not input_spec:
            return report

        # 检查 required_fields
        required = input_spec.get("required_fields", [])
        for field_name in required:
            if field_name not in actual_data or actual_data[field_name] is None:
                result = CheckResult(
                    check_type="required_field_missing",
                    severity="reject",
                    passed=False,
                    message=f"缺少必填字段: {field_name}",
                )
                report.results.append(result)
                report.passed = False
                report.blocking_failures.append("required_field_missing")

        # 检查 file_constraints
        file_constraints = input_spec.get("file_constraints", {})
        if file_constraints and "file_url" in actual_data:
            file_size_mb = actual_data.get("file_size_mb", 0)
            file_type = actual_data.get("file_type", "")

            max_size = file_constraints.get("max_size_mb", 100)
            if file_size_mb > max_size:
                result = CheckResult(
                    check_type="file_size_exceeded",
                    severity="reject",
                    passed=False,
                    message=f"文件大小 {file_size_mb}MB 超过限制 {max_size}MB",
                )
                report.results.append(result)
                report.passed = False
                report.blocking_failures.append("file_size_exceeded")

            allowed_formats = file_constraints.get("allowed_formats", [])
            if allowed_formats and file_type not in allowed_formats:
                result = CheckResult(
                    check_type="file_format_invalid",
                    severity="reject",
                    passed=False,
                    message=f"文件格式 '{file_type}' 不在允许列表: {allowed_formats}",
                )
                report.results.append(result)
                report.passed = False
                report.blocking_failures.append("file_format_invalid")

        # 检查 data_constraints
        data_constraints = input_spec.get("data_constraints", {})
        if data_constraints:
            min_fields = data_constraints.get("min_json_fields", [])
            missing = [f for f in min_fields if f not in actual_data]
            if missing:
                result = CheckResult(
                    check_type="data_fields_missing",
                    severity="reject_with_feedback",
                    passed=False,
                    message=f"缺少数据字段: {missing}",
                    details={"missing_fields": missing},
                )
                report.results.append(result)
                report.passed = False
                report.blocking_failures.append("data_fields_missing")

        # 执行 quality_checks（自定义检查项）
        quality_checks = input_spec.get("quality_checks", [])
        for qc in quality_checks:
            qc_type = qc.get("type", "")
            severity = qc.get("severity", "reject")

            if qc_type == "file_not_empty":
                is_empty = not actual_data.get("file_url") and not actual_data.get("content")
                if is_empty:
                    result = CheckResult(
                        check_type="file_not_empty",
                        severity=severity,
                        passed=False,
                        message=qc.get("message", "文件为空"),
                    )
                    report.results.append(result)
                    report.passed = False
                    if severity in ("reject", "block"):
                        report.blocking_failures.append("file_not_empty")
            elif qc_type == "field_completeness":
                fields = qc.get("fields", [])
                min_ratio = qc.get("min_ratio", 0.8)
                present = sum(1 for f in fields if f in actual_data and actual_data[f])
                ratio = present / len(fields) if fields else 1.0
                is_ok = ratio >= min_ratio
                if not is_ok:
                    missing_f = [f for f in fields if f not in actual_data or not actual_data[f]]
                    msg = qc.get("message", "").format(
                        ratio=f"{ratio:.0%}", missing_fields=missing_f
                    )
                    result = CheckResult(
                        check_type="field_completeness",
                        severity=severity,
                        passed=False,
                        message=msg,
                    )
                    report.results.append(result)
                    report.passed = False
                    if severity in ("reject", "reject_with_feedback", "block"):
                        report.blocking_failures.append("field_completeness")

        return report


class OutputSpecChecker:
    """检查流程输出是否符合 output_spec 规范。"""

    def check(self, output_spec: dict, actual_output: dict) -> SpecCheckReport:
        """执行输出规范检查。

        Args:
            output_spec: flow 的 output_spec JSON
            actual_output: 实际产出数据 {artifact_name: content, ...}

        Returns:
            SpecCheckReport
        """
        report = SpecCheckReport(passed=True)

        if not output_spec:
            return report

        # 检查 required_artifacts
        required_artifacts = output_spec.get("required_artifacts", [])
        for artifact in required_artifacts:
            name = artifact.get("name", "")
            is_mandatory = artifact.get("mandatory", True)

            if is_mandatory and name not in actual_output:
                result = CheckResult(
                    check_type="artifact_missing",
                    severity="block",
                    passed=False,
                    message=f"缺少必要产出物: {name}",
                )
                report.results.append(result)
                report.passed = False
                report.blocking_failures.append("artifact_missing")
            elif is_mandatory and name in actual_output:
                # 检查文档非空
                content = actual_output[name]
                if not content or (isinstance(content, str) and not content.strip()):
                    result = CheckResult(
                        check_type="document_empty",
                        severity="block",
                        passed=False,
                        message=f"文档 '{name}' 为空",
                    )
                    report.results.append(result)
                    report.passed = False
                    report.blocking_failures.append("document_empty")

        # 执行 output quality_checks
        quality_checks = output_spec.get("quality_checks", [])
        for qc in quality_checks:
            qc_type = qc.get("type", "")
            severity = qc.get("severity", "block")

            if qc_type == "all_fields_populated":
                fields = qc.get("fields", [])
                empty_fields = [f for f in fields if f not in actual_output or not actual_output[f]]
                if empty_fields:
                    result = CheckResult(
                        check_type="fields_not_populated",
                        severity=severity,
                        passed=False,
                        message=qc.get("message", "").format(empty_fields=empty_fields),
                    )
                    report.results.append(result)
                    report.passed = False
                    report.blocking_failures.append("fields_not_populated")

        # 检查 approval_gating
        approval_gating = output_spec.get("approval_gating", {})
        if approval_gating.get("require_output_spec_met") and not report.passed:
            # 输出未达标，标记为 draft_incomplete
            report.blocking_failures.append("output_spec_not_met")

        return report


def generate_rejection_message(
    flow_name: str, node_name: str, agent_name: str,
    report: SpecCheckReport, spec: dict
) -> str:
    """生成结构化拒绝通知消息。"""
    lines = [
        "⛔ 输入数据质量检查未通过",
        "",
        f"流程：{flow_name}",
        f"节点：{node_name}（{agent_name}）",
        "失败项：",
    ]

    for i, r in enumerate(report.results, 1):
        if not r.passed:
            lines.append(f"{i}. {r.check_type}: {r.message}")

    lines.extend(["", "规范要求："])
    fc = spec.get("file_constraints", {})
    if fc:
        if fc.get("allowed_formats"):
            lines.append(f"- 文件格式：{fc['allowed_formats']}")
        if fc.get("max_size_mb"):
            lines.append(f"- 最大大小：{fc['max_size_mb']}MB")
        if fc.get("min_dpi"):
            lines.append(f"- 最低 DPI：{fc['min_dpi']}")
    rf = spec.get("required_fields", [])
    if rf:
        lines.append(f"- 必填字段：{rf}")

    lines.extend(["", "请修正后重新提交。"])
    return "\n".join(lines)
