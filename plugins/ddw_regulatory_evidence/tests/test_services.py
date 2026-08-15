"""Tests for Regulatory Evidence service."""


class TestDocumentCRUD:
    def test_add_document(self, service):
        doc = service.add_document(
            title="EU Novel Food Regulation", content="...",
            jurisdiction="EU", authority="EU_Commission",
            doc_type="regulation", category="novel_food",
            reference_number="Regulation (EU) 2015/2283"
        )
        assert doc.id is not None
        assert doc.jurisdiction == "EU"

    def test_list_by_jurisdiction(self, service):
        service.add_document(title="CN", content="...", jurisdiction="CN",
                             authority="NHC", doc_type="regulation")
        service.add_document(title="EU", content="...", jurisdiction="EU",
                             authority="EFSA", doc_type="guidance")
        cn_docs = service.list_documents(jurisdiction="CN")
        assert len(cn_docs) == 1

    def test_search(self, service):
        service.add_document(title="Novel Food Authorization", content="CABIO-A-2藻油DHA",
                             jurisdiction="EU", authority="EU_Commission",
                             doc_type="approval")
        results = service.search_documents("CABIO-A-2")
        assert len(results) >= 1


class TestEvidenceChains:
    def test_create_chain(self, service):
        chain = service.create_evidence_chain(
            requirement="HACCP体系有效运行",
            product_name="藻油DHA",
            compliance_status="compliant"
        )
        assert chain.id is not None
        assert chain.compliance_status == "compliant"

    def test_list_chains_by_product(self, service):
        service.create_evidence_chain(requirement="R1", product_name="DHA")
        service.create_evidence_chain(requirement="R2", product_name="ARA")
        dha_chains = service.list_evidence_chains(product_name="DHA")
        assert len(dha_chains) == 1

    def test_update_chain(self, service):
        chain = service.create_evidence_chain(
            requirement="Test", compliance_status="pending")
        updated = service.update_evidence_chain(chain.id, compliance_status="compliant")
        assert updated.compliance_status == "compliant"

    def test_filter_by_compliance_status(self, service):
        service.create_evidence_chain(requirement="R1", compliance_status="compliant")
        service.create_evidence_chain(requirement="R2", compliance_status="pending")
        service.create_evidence_chain(requirement="R3", compliance_status="non_compliant")
        pending = service.list_evidence_chains(compliance_status="pending")
        assert len(pending) == 1


class TestSeedData:
    def test_seed_regulations(self, service):
        count = service.seed_food_regulations()
        assert count >= 6
        cn_docs = service.list_documents(jurisdiction="CN")
        assert len(cn_docs) >= 2

    def test_seed_cabio_template(self, service):
        count = service.seed_cabio_evidence_template()
        assert count >= 4
        dha_chains = service.list_evidence_chains(product_name="CABIO-A-2 DHA藻油")
        assert len(dha_chains) >= 1
