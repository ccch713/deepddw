"""碳硅协作 P2 测试用例：spec_checker 引擎。"""
from plugins.ddw_flow_designer.services.spec_checker import (
    InputSpecChecker,
    OutputSpecChecker,
    generate_rejection_message,
    SpecCheckReport,
    CheckResult,
)


class TestInputSpecChecker:
    """P2.1: InputSpecChecker 测试。"""

    def setup_method(self):
        self.checker = InputSpecChecker()

    def test_p2_t1_empty_spec_passes(self):
        """空 spec = 全部通过"""
        report = self.checker.check({}, {"any": "data"})
        assert report.passed is True

    def test_p2_t2_required_field_missing_rejects(self):
        """缺少必填字段 → reject"""
        spec = {"required_fields": ["file_url", "company_name"]}
        report = self.checker.check(spec, {"file_url": "http://x.com/a.pdf"})
        assert report.passed is False
        assert "required_field_missing" in report.blocking_failures

    def test_p2_t3_file_size_exceeded_rejects(self):
        """文件超大 → reject"""
        spec = {"file_constraints": {"max_size_mb": 10}}
        data = {"file_url": "http://x.com/a.pdf", "file_size_mb": 50, "file_type": "pdf"}
        report = self.checker.check(spec, data)
        assert report.passed is False
        assert "file_size_exceeded" in report.blocking_failures

    def test_p2_t4_file_format_invalid_rejects(self):
        """非法文件格式 → reject"""
        spec = {"file_constraints": {"allowed_formats": ["pdf", "jpg"]}}
        data = {"file_url": "http://x.com/a.docx", "file_type": "docx"}
        report = self.checker.check(spec, data)
        assert report.passed is False

    def test_p2_t5_all_checks_pass(self):
        """全部检查通过"""
        spec = {
            "required_fields": ["file_url", "company_name"],
            "file_constraints": {"max_size_mb": 20, "allowed_formats": ["pdf"]},
            "data_constraints": {"min_json_fields": ["company_name", "amount"]},
        }
        data = {
            "file_url": "http://x.com/a.pdf",
            "file_size_mb": 5,
            "file_type": "pdf",
            "company_name": "测试公司",
            "amount": 1000,
        }
        report = self.checker.check(spec, data)
        assert report.passed is True


class TestOutputSpecChecker:
    """P2.2: OutputSpecChecker 测试。"""

    def setup_method(self):
        self.checker = OutputSpecChecker()

    def test_p2_t6_mandatory_artifact_missing_blocks(self):
        """缺少必要产出物 → block"""
        spec = {
            "required_artifacts": [
                {"type": "document", "name": "审查报告", "mandatory": True},
            ],
        }
        report = self.checker.check(spec, {"其他数据": "xxx"})
        assert report.passed is False
        assert "artifact_missing" in report.blocking_failures

    def test_p2_t7_empty_document_blocks(self):
        """文档为空 → block"""
        spec = {
            "required_artifacts": [
                {"type": "document", "name": "报告", "mandatory": True},
            ],
            "quality_checks": [
                {"type": "document_not_empty", "severity": "block", "message": "文档为空"},
            ],
        }
        report = self.checker.check(spec, {"报告": ""})
        assert report.passed is False

    def test_p2_t7_valid_output_passes(self):
        """有效输出通过"""
        spec = {
            "required_artifacts": [
                {"type": "document", "name": "报告", "mandatory": True},
            ],
        }
        report = self.checker.check(spec, {"报告": "这是报告内容"})
        assert report.passed is True


class TestGenerateRejectionMessage:
    """P2.3: 拒绝消息生成测试。"""

    def test_generates_message_with_failures(self):
        """生成包含失败项的拒绝消息"""
        report = SpecCheckReport(
            passed=False,
            results=[
                CheckResult(
                    check_type="required_field_missing",
                    severity="reject",
                    passed=False,
                    message="缺少必填字段: file_url",
                ),
            ],
            blocking_failures=["required_field_missing"],
        )
        spec = {
            "required_fields": ["file_url"],
            "file_constraints": {"allowed_formats": ["pdf"], "max_size_mb": 10},
        }
        msg = generate_rejection_message("测试流程", "节点1", "AI助手", report, spec)
        assert "file_url" in msg
        assert "测试流程" in msg
        assert "节点1" in msg
