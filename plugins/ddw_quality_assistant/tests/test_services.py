"""Tests for Quality Assistant service."""


class Test8DGeneration:
    def test_generate_8d_basic(self, service):
        doc = service.generate_8d_report(problem="产品颜色异常")
        assert doc.id is not None
        assert doc.doc_type == "8d"
        assert "8D" in doc.content
        assert doc.status == "draft"

    def test_generate_8d_with_details(self, service):
        doc = service.generate_8d_report(
            problem="DHA藻油氧化值超标", product="ARA粉剂",
            batch="20260801-A", severity="critical"
        )
        assert doc.id is not None
        assert "DHA" in doc.content
        assert doc.input_data["severity"] == "critical"

    def test_list_documents(self, service):
        service.generate_8d_report(problem="test1")
        service.generate_8d_report(problem="test2")
        docs = service.list_documents(doc_type="8d")
        assert len(docs) == 2


class TestCAPAGeneration:
    def test_generate_capa(self, service):
        doc = service.generate_capa_draft(nonconformity="车间温湿度记录缺失")
        assert doc.id is not None
        assert doc.doc_type == "capa"
        assert "CAPA" in doc.content

    def test_generate_capa_from_audit(self, service):
        doc = service.generate_capa_draft(
            nonconformity="HACCP关键控制点监控频率不足",
            source="external_audit", severity="critical"
        )
        assert "HACCP" in doc.content


class TestDeviationReport:
    def test_generate_deviation(self, service):
        doc = service.generate_deviation_report(
            deviation_desc="发酵罐温度偏差+2°C持续30分钟"
        )
        assert doc.doc_type == "deviation"
        assert "偏差" in doc.content


class TestComplaintReply:
    def test_generate_reply(self, service):
        doc = service.generate_complaint_reply(
            complaint="产品有异味", customer="某乳业公司"
        )
        assert doc.doc_type == "complaint"
        assert "某乳业公司" in doc.content


class TestFiveWhy:
    def test_perform_5why(self, service):
        analysis = service.perform_5why_analysis(problem="产品微生物超标")
        assert analysis.id is not None
        assert len(analysis.why_chain) == 5
        assert analysis.root_cause != ""

    def test_list_5why(self, service):
        service.perform_5why_analysis(problem="test1")
        service.perform_5why_analysis(problem="test2")
        analyses = service.list_5why_analyses()
        assert len(analyses) == 2


class TestDocumentStatus:
    def test_update_status(self, service):
        doc = service.generate_8d_report(problem="test status")
        assert doc.status == "draft"
        updated = service.update_document_status(doc.id, "reviewed")
        assert updated.status == "reviewed"

    def test_update_nonexistent(self, service):
        result = service.update_document_status(9999, "reviewed")
        assert result is None
