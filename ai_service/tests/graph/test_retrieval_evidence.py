import json
import unittest

from app.reasoning.retrieval_evidence import add_retrieval_evidence, ground_hypotheses_in_evidence, label_tool_evidence
from app.graph.pre_diagnosis_schemas import ReflectHypothesis
from app.tools.hybrid_retrieval.fusion import book_result

_TRIPLE = {"subject": "allergic contact dermatitis", "relation": "DISEASE_PHENOTYPE_POSITIVE", "object": "Eczema", "display": None, "evidence": "Viêm da tiếp xúc dị ứng biểu hiện bằng dát đỏ", "pages": [122], "document_id": "d1"}


class DocumentGraphEvidenceTest(unittest.TestCase):
    def test_triple_with_quote_is_evidence_with_page(self) -> None:
        items = label_tool_evidence("query_document_graph", json.dumps({"evidence_found": True, "triples": [_TRIPLE]}))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["kind"], "evidence")
        self.assertEqual(items[0]["source"], "đồ thị sách, trang 122")
        self.assertIn("Viêm da tiếp xúc dị ứng", items[0]["text"])

    def test_triple_without_quote_is_skipped(self) -> None:
        triples = [{**_TRIPLE, "evidence": ""}, {**_TRIPLE, "evidence": None}]
        self.assertEqual(label_tool_evidence("query_document_graph", json.dumps({"triples": triples})), [])

    def test_not_found_and_invalid_json(self) -> None:
        self.assertEqual(label_tool_evidence("query_document_graph", json.dumps({"evidence_found": False, "note": "x"})), [])
        self.assertEqual(label_tool_evidence("query_document_graph", "không phải json"), [])

    def test_cite_passes_ground_hypotheses(self) -> None:
        evidence: list[dict] = []
        add_retrieval_evidence(evidence, label_tool_evidence("query_document_graph", json.dumps({"triples": [_TRIPLE]})))
        hypothesis = ReflectHypothesis(disease="Eczema", confidence="vừa", cites=[evidence[0]["id"]], missing=[])
        plan, unsupported, _ = ground_hypotheses_in_evidence([hypothesis], evidence)
        self.assertEqual([p["disease"] for p in plan], ["Eczema"])
        self.assertEqual(unsupported, [])


class BookCitationRefTest(unittest.TestCase):
    _PAYLOAD = {"document_id": "d1", "document_title": "Sách", "chunk_id": "c9", "toc_path": ["Chương 5", "Chàm"], "page_start": 130, "page_end": 131,
                "page_printed_start": 120, "page_printed_end": 121, "text": "Nội dung đoạn"}

    def test_book_result_carries_trace_ids_and_pdf_pages(self) -> None:
        r = book_result(self._PAYLOAD)
        self.assertEqual((r["document_id"], r["chunk_id"], r["page_start"], r["page_end"]), ("d1", "c9", 130, 131))
        self.assertEqual(r["pages"], "tr.120-121")  # trang in vẫn giữ nguyên để hiển thị

    def test_book_evidence_gets_ref_and_text_has_no_ids(self) -> None:
        items = label_tool_evidence("hybrid_retrieval", json.dumps({"results": [{"rank": 1, "score": 0.5, **book_result(self._PAYLOAD)}]}))
        self.assertEqual(items[0]["ref"], {"document_id": "d1", "chunk_id": "c9", "page_start": 130, "page_end": 131})
        self.assertNotIn("chunk_id", items[0]["text"])

    def test_non_book_and_legacy_results_have_no_ref(self) -> None:
        kg = {"source": "kg", "text": "Eczema liên quan ngứa"}
        legacy_book = {"source": "book", "title": "Sách", "section": "Chàm", "pages": "tr.1", "text": "x"}
        items = label_tool_evidence("hybrid_retrieval", json.dumps({"results": [kg, legacy_book]}))
        self.assertTrue(all("ref" not in i for i in items))


if __name__ == "__main__":
    unittest.main()
