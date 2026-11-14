import asyncio
import json
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from app.context.agent_context import AgentContext
from app.reasoning.retrieval_evidence import label_tool_evidence
from app.tools.query_patient_graph import query_patient_graph

CONTEXT = {
    "matched": [], "unmatched": ["khó chịu"], "notes": [],
    "candidates": [{"name": "eczema", "score": 3.1, "why": ["triệu chứng: Pruritus"], "absent": ["Fever"]}],
    "questions": [{"phenotype": "Xerosis", "present_in": ["eczema"], "absent_in": ["acne"]}],
    "drug_notes": ["Thuốc đang dùng Ibuprofen có thể gây Pruritus (tác dụng phụ ghi trong đồ thị)."],
    "book_evidence": [{"disease": "eczema", "relation": "phenotype present", "object": "Pruritus", "evidence": "Ngứa là triệu chứng chính", "pages": [12, 13], "document_id": "d1"},
                      {"disease": "eczema", "relation": "x", "object": "y", "evidence": " ", "pages": []}],
}


def call(ctx: AgentContext, knowledge: Any, **args: Any) -> dict[str, Any]:
    runtime = SimpleNamespace(context=ctx)
    with patch("app.tools.query_patient_graph.get_knowledge_client", lambda: knowledge), patch("app.reasoning.patient_fact_store.get_knowledge_client", lambda: knowledge):
        raw = asyncio.run(query_patient_graph.coroutine(runtime=runtime, **args))  # type: ignore[attr-defined]
    return json.loads(raw)


class QueryPatientGraphToolTest(unittest.TestCase):
    def test_saves_this_turns_facts_first_then_queries_graph(self) -> None:
        knowledge = AsyncMock()
        knowledge.apply_patient_facts.return_value = {"applied": 1, "skipped": [], "lesions": []}
        knowledge.get_patient_graph_context.return_value = CONTEXT
        ctx = AgentContext(user_id="u", conversation_id="c", patient_profile_id="pp-1", message_id="m1")
        ctx.turn_facts = [{"template_label": "ngứa", "category": 1, "lesion": "L1"}]
        data = call(ctx, knowledge, top_k=99)
        self.assertEqual(knowledge.mock_calls[0][0], "apply_patient_facts")  # ghi trước, truy vấn sau
        knowledge.get_patient_graph_context.assert_awaited_once_with("pp-1", 8)
        self.assertTrue(ctx.turn_facts_saved)
        self.assertTrue(data["evidence_found"])
        self.assertEqual(data["candidates"][0]["name"], "eczema")

    def test_no_profile_and_failure_are_reported_not_raised(self) -> None:
        knowledge = AsyncMock()
        self.assertFalse(call(AgentContext(user_id="u", conversation_id="c"), knowledge)["evidence_found"])
        knowledge.get_patient_graph_context.assert_not_awaited()
        knowledge.get_patient_graph_context.side_effect = RuntimeError("knowledge chết")
        with self.assertLogs("agent.tools.query_patient_graph", level="ERROR"):
            data = call(AgentContext(user_id="u", conversation_id="c", patient_profile_id="pp-1"), knowledge)
        self.assertIn("knowledge chết", data["error"])

    def test_empty_graph_context_is_not_evidence(self) -> None:
        knowledge = AsyncMock()
        knowledge.get_patient_graph_context.return_value = {**CONTEXT, "candidates": [], "questions": [], "drug_notes": [], "book_evidence": []}
        self.assertFalse(call(AgentContext(user_id="u", conversation_id="c", patient_profile_id="pp-1"), knowledge)["evidence_found"])


class LabelPatientGraphTest(unittest.TestCase):
    def test_only_book_quotes_are_evidence(self) -> None:
        items = label_tool_evidence("query_patient_graph", json.dumps({"evidence_found": True, **CONTEXT}))
        kinds = [i["kind"] for i in items]
        self.assertEqual(kinds, ["hint", "hint", "hint", "evidence"])  # câu trích rỗng bị bỏ
        self.assertIn("KHÔNG có: Fever", items[0]["text"])
        self.assertEqual(items[3]["source"], "đồ thị sách, trang 12, 13")
        self.assertIn("“Ngứa là triệu chứng chính”", items[3]["text"])

    def test_not_found_or_bad_json_gives_nothing(self) -> None:
        self.assertEqual(label_tool_evidence("query_patient_graph", json.dumps({"evidence_found": False})), [])
        self.assertEqual(label_tool_evidence("query_patient_graph", "không phải json"), [])


if __name__ == "__main__":
    unittest.main()
