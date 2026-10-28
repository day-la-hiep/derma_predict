import json
import unittest

from agent.graph.v2.evidence import add_evidence, ground_hypotheses, label_evidence
from agent.graph.v2.schemas import ReflectHypothesis

_TRIPLE = {"subject": "allergic contact dermatitis", "relation": "DISEASE_PHENOTYPE_POSITIVE", "object": "Eczema", "display": None, "evidence": "Viêm da tiếp xúc dị ứng biểu hiện bằng dát đỏ", "pages": [122], "document_id": "d1"}


class DocumentGraphEvidenceTest(unittest.TestCase):
    def test_triple_with_quote_is_evidence_with_page(self) -> None:
        items = label_evidence("query_document_graph", json.dumps({"evidence_found": True, "triples": [_TRIPLE]}))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["kind"], "evidence")
        self.assertEqual(items[0]["source"], "đồ thị sách, trang 122")
        self.assertIn("Viêm da tiếp xúc dị ứng", items[0]["text"])

    def test_triple_without_quote_is_skipped(self) -> None:
        triples = [{**_TRIPLE, "evidence": ""}, {**_TRIPLE, "evidence": None}]
        self.assertEqual(label_evidence("query_document_graph", json.dumps({"triples": triples})), [])

    def test_not_found_and_invalid_json(self) -> None:
        self.assertEqual(label_evidence("query_document_graph", json.dumps({"evidence_found": False, "note": "x"})), [])
        self.assertEqual(label_evidence("query_document_graph", "không phải json"), [])

    def test_cite_passes_ground_hypotheses(self) -> None:
        evidence: list[dict] = []
        add_evidence(evidence, label_evidence("query_document_graph", json.dumps({"triples": [_TRIPLE]})))
        hypothesis = ReflectHypothesis(disease="Eczema", confidence="vừa", cites=[evidence[0]["id"]], missing=[])
        plan, unsupported, _ = ground_hypotheses([hypothesis], evidence)
        self.assertEqual([p["disease"] for p in plan], ["Eczema"])
        self.assertEqual(unsupported, [])


if __name__ == "__main__":
    unittest.main()
