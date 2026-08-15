"""Tests for Quality Knowledge service."""


class TestDocumentCRUD:
    def test_add_document(self, service):
        doc = service.add_document(
            title="HACCP七大原理", content="HACCP七大原理详细说明...",
            doc_type="standard", category="haccp", tags=["HACCP"]
        )
        assert doc.id is not None
        assert doc.title == "HACCP七大原理"

    def test_get_document(self, service):
        doc = service.add_document(title="Test", content="Content", doc_type="sop")
        fetched = service.get_document(doc.id)
        assert fetched.title == "Test"

    def test_update_document(self, service):
        doc = service.add_document(title="Old", content="Old content", doc_type="sop")
        updated = service.update_document(doc.id, title="New", content="New content")
        assert updated.title == "New"

    def test_delete_document(self, service):
        doc = service.add_document(title="Delete me", content="...", doc_type="sop")
        assert service.delete_document(doc.id) is True
        assert service.get_document(doc.id) is None

    def test_list_documents(self, service):
        service.add_document(title="Doc1", content="...", doc_type="standard")
        service.add_document(title="Doc2", content="...", doc_type="sop")
        docs = service.list_documents()
        assert len(docs) == 2

    def test_list_filter_by_type(self, service):
        service.add_document(title="Std", content="...", doc_type="standard")
        service.add_document(title="Sop", content="...", doc_type="sop")
        docs = service.list_documents(doc_type="standard")
        assert len(docs) == 1
        assert docs[0].doc_type == "standard"


class TestSearch:
    def test_keyword_search(self, service):
        service.add_document(title="HACCP原理", content="危害分析与关键控制点", doc_type="standard")
        service.add_document(title="ISO 22000", content="食品安全管理体系", doc_type="standard")
        results = service.search("HACCP")
        assert len(results) >= 1
        assert any("HACCP" in r.title for r in results)

    def test_search_with_filter(self, service):
        service.add_document(title="HACCP Std", content="...", doc_type="standard", category="haccp")
        service.add_document(title="HACCP SOP", content="...", doc_type="sop", category="haccp")
        results = service.search("HACCP", doc_type="sop")
        assert len(results) == 1
        assert results[0].doc_type == "sop"

    def test_semantic_search(self, service):
        service.add_document(title="温度控制", content="发酵过程温度监控要点和发酵温度偏高处理", doc_type="sop")
        results = service.semantic_search("发酵温度")
        assert len(results) >= 1


class TestSeedData:
    def test_seed_food_safety(self, service):
        count = service.seed_food_safety_standards()
        assert count > 0
        docs = service.list_documents()
        assert len(docs) >= 8

    def test_seed_idempotent(self, service):
        service.seed_food_safety_standards()
        service.seed_food_safety_standards()
        docs = service.list_documents()
        titles = [d.title for d in docs]
        assert len(titles) == len(set(titles))  # no duplicates


class TestSearchStats:
    def test_search_stats(self, service):
        service.search("test1")
        service.search("test2")
        service.search("test1")
        stats = service.get_search_stats()
        assert stats["total_searches"] == 3
