import asyncio
import unittest
from typing import Any, cast
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.reasoning.patient_fact_extractor import (
    ExtractedFact,
    ExtractedFacts,
    assign_lesions,
    build_fact_from_graph,
    build_graph_fact,
    extract_facts,
    fact_key,
    facts_text,
    get_facts_fingerprint,
    merge_facts,
    validate_facts_evidence,
)
from app.context.agent_context import AgentContext
from app.common.tracing import build_run_config
from app.graph.chat_graph import build_chat_graph
from app.graph.v2.pre_diagnosis_graph import _after_plan
from app.state.v2.pre_diagnosis_state import PreDiagnosisState
from app.config.settings import settings


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def fact(label: str, detail: str, kind: str = "symptom") -> dict[str, Any]:
    return {"template_label": label, "fact_type": kind, "detail": detail, "source_messages": []}


class FakeStructured:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls = 0

    async def ainvoke(self, _messages: Any) -> Any:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeModel:
    def __init__(self, structured: FakeStructured) -> None:
        self.structured = structured

    def with_structured_output(self, *_args: Any, **_kwargs: Any) -> FakeStructured:
        return self.structured


class MergeFactsTest(unittest.TestCase):
    def test_newer_fact_overrides_same_label(self):
        merged = merge_facts([fact("Ngứa", "ít")], [fact("ngứa ", "nhiều về đêm")])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["detail"], "nhiều về đêm")

    def test_same_label_different_type_kept(self):
        taking = {**fact("Penicillin", "đang dùng", "medication"), "category": 5, "object_type": "drug", "kind": "taking"}
        allergy = {**fact("Penicillin", "dị ứng", "allergy"), "category": 5, "object_type": "drug", "kind": "allergy"}
        self.assertEqual(len(merge_facts([taking], [allergy])), 2)

    def test_same_label_in_two_lesions_kept(self):
        merged = merge_facts([{**fact("Ngứa", "ít"), "category": 1, "lesion": "L1"}], [{**fact("Ngứa", "nhiều"), "category": 1, "lesion": "L2"}])
        self.assertEqual(len(merged), 2)

    def test_single_valued_attribute_replaced_by_name(self):
        size = lambda value: {**fact(value, ""), "category": 3, "name": "kích thước", "lesion": "L1"}  # noqa: E731
        merged = merge_facts([size("1 cm")], [size("3 cm")])
        self.assertEqual([f["template_label"] for f in merged], ["3 cm"])

    def test_legacy_fact_without_category_still_merges(self):
        self.assertEqual(fact_key(fact("Ngứa", "x")), ("1", "", "ngứa"))

    def test_capped_to_latest(self):
        merged = merge_facts([], [fact(f"f{i}", "x") for i in range(50)])
        self.assertEqual(len(merged), 30)
        self.assertEqual(merged[-1]["template_label"], "f49")

    def test_validate_drops_bad_indices(self):
        out = validate_facts_evidence([{"template_label": "Ngứa", "category": 1, "detail": "tay", "source_messages": [1, 5, "a"]}], ["ngứa ở tay"])
        self.assertEqual(out[0]["source_messages"], [1])
        self.assertEqual((out[0]["fact_type"], out[0]["present"], out[0]["kg_node_id"]), ("symptom", True, None))

    def test_validate_drops_invalid_category_and_normalizes_enums(self):
        out = validate_facts_evidence(
            [
                {"template_label": "x", "category": 99},
                {"template_label": "dát", "category": 2, "object_type": "khong-co", "scope": "la", "name": "  Màu ", "present": 0},
                {"template_label": "đỏ", "category": 3, "name": " Màu  Sắc "},
                {"template_label": "đối xứng", "category": 3, "name": "Phân bố"},
                {"template_label": "nắng", "category": 4, "effect": "bịa"},
            ],
            [],
        )
        self.assertEqual([f["template_label"] for f in out], ["dát", "đỏ", "đối xứng", "nắng"])
        self.assertEqual((out[0]["object_type"], out[0]["scope"], out[0]["present"]), ("effect/phenotype", "skin", False))  # nhóm 2 mặc định phenotype
        self.assertEqual(out[1]["object_type"], "")  # nhóm 3 là giá trị chữ, không khớp nút
        self.assertEqual((out[0]["kind"], out[3]["effect"], out[3]["fact_type"]), ("primary", "", "history"))  # effect sai thì thành phơi nhiễm
        self.assertEqual((out[1]["name"], out[2]["name"]), ("màu sắc", "distribution"))  # alias tiếng Việt về tên chuẩn

    def test_history_defaults_match_stored_facts_so_keys_merge(self):
        raw = [
            {"template_label": "penicillin", "category": 5, "object_type": "drug", "kind": "", "of": ""},
            {"template_label": "chàm", "category": 5, "object_type": "disease", "kind": "taking", "of": "mẹ"},
        ]
        out = validate_facts_evidence(raw, [])
        self.assertEqual([(f["kind"], f["of"], f["fact_type"]) for f in out], [("taking", "", "medication"), ("", "self", "history")])
        stored = build_fact_from_graph({"lesion_id": None, "category": 5, "relation": "PT_TAKES_DRUG", "label": "Penicillin", "object_type": "drug", "kind": "taking", "of": ""}, [])
        self.assertEqual(fact_key(stored), fact_key(out[0]))  # fact lưu trong graph và fact mới trích cùng khoá

    def test_assign_lesions_groups_by_temp_key_and_keeps_known(self):
        facts = [
            {**fact("ngứa", "x"), "category": 1, "lesion": "moi-1", "site_text": "khuỷu tay"},
            {**fact("dát đỏ", "x"), "category": 2, "lesion": "moi-1"},
            {**fact("ngứa", "y"), "category": 1, "lesion": "moi-2", "site_text": "bàn chân"},
            {**fact("khó chịu", "z"), "category": 1, "lesion": "L-cu"},
            {**fact("sốt", "z"), "category": 1, "scope": "body", "lesion": "moi-1"},
        ]
        out = assign_lesions(facts, [{"id": "L-cu", "site_text": "mặt"}])
        self.assertEqual(out[0]["lesion"], out[1]["lesion"])
        self.assertNotEqual(out[0]["lesion"], out[2]["lesion"])
        self.assertEqual((out[3]["lesion"], out[4]["lesion"]), ("L-cu", ""))
        self.assertEqual((out[1]["site_text"], out[2]["site_text"]), ("khuỷu tay", "bàn chân"))

    def test_assign_lesions_without_ref_uses_last_known_or_creates_one(self):
        loose = lambda: [{**fact("ngứa", "x"), "category": 1, "lesion": ""}]  # noqa: E731
        self.assertEqual(assign_lesions(loose(), [{"id": "A"}, {"id": "B"}])[0]["lesion"], "B")
        created = assign_lesions(loose(), [])[0]["lesion"]
        self.assertTrue(created and created not in ("A", "B"))

    def test_location_fact_names_the_new_lesion(self):
        facts = [{**fact("mặt trong khuỷu tay", ""), "category": 3, "name": "location", "lesion": "moi-1"}, {**fact("ngứa", ""), "category": 1, "lesion": "moi-1"}]
        out = assign_lesions(facts, [])
        self.assertEqual(out[1]["site_text"], "mặt trong khuỷu tay")

    def test_facts_text_marks_absent_resolved_and_site(self):
        text = facts_text([
            {**fact("ngứa", "về đêm"), "category": 1, "site_text": "tay", "onset_text": "2 tuần"},
            {**fact("sốt", ""), "category": 1, "scope": "body", "present": False},
            {**fact("ngứa", ""), "category": 1, "resolved": True},
        ])
        self.assertIn("- [triệu chứng @tay] ngứa: về đêm (khởi phát: 2 tuần)", text)
        self.assertIn("KHÔNG CÓ sốt", text)
        self.assertIn("ngứa (đã hết)", text)

    def test_fingerprint_changes_with_facts(self):
        base = [{**fact("ngứa", "ít"), "category": 1, "lesion": "L1"}]
        same = [{**fact("ngứa", "ít"), "category": 1, "lesion": "L1"}]
        self.assertEqual(get_facts_fingerprint(base), get_facts_fingerprint(same))
        for changed in (
            [{**base[0], "detail": "nhiều"}], [{**base[0], "present": False}], [{**base[0], "resolved": True}], [*base, {**fact("đau", ""), "category": 1, "lesion": "L1"}],
        ):
            self.assertNotEqual(get_facts_fingerprint(base), get_facts_fingerprint(changed))

    def test_graph_roundtrip_keeps_key_and_fields(self):
        graph = {"lesion_id": "L1", "category": 1, "relation": "PT_HAS_SYMPTOM", "label": "ngứa", "detail": "đêm", "object_type": "effect/phenotype",
                 "kg_node_id": "989", "present": False, "status": "current", "name": "", "kind": "", "effect": "", "of": "", "onset_text": "2 tuần",
                 "source_message_id": "m1", "link_method": "llm"}
        known = build_fact_from_graph(graph, [{"id": "L1", "site_text": "tay", "scope": "skin"}])
        sent = build_graph_fact(known)
        self.assertEqual((known["site_text"], known["present"], known["fact_type"]), ("tay", False, "symptom"))
        self.assertEqual(
            (sent["category"], sent["lesion_id"], sent["kg_node_id"], sent["present"], sent["source_message_id"], sent["link_method"]),
            (1, "L1", "989", False, "m1", "llm"),
        )
        new = {**fact("ngứa", "x"), "category": 1, "lesion": "L1"}
        self.assertEqual(fact_key(known), fact_key(new))


class ExtractFactsTest(unittest.TestCase):
    def _run(self, result: Any, transcript: list[tuple[str, str]]) -> tuple[list[dict[str, Any]], FakeStructured]:
        structured = FakeStructured(result)
        with patch("app.reasoning.patient_fact_extractor.get_model", return_value=FakeModel(structured)):
            return run(extract_facts([], transcript)), structured

    def test_skips_llm_without_patient_message(self):
        out, s = self._run(ExtractedFacts(), [("AI", "Chào bạn")])
        self.assertEqual((out, s.calls), ([], 0))

    def test_returns_validated_facts(self):
        result = ExtractedFacts(facts=[ExtractedFact(template_label="Ngứa", category=1, detail="hai tay", site_text="hai tay", lesion="moi-1", source_messages=[1, 9])])
        out, _ = self._run(result, [("PATIENT", "tôi ngứa hai tay")])
        self.assertEqual(out[0]["source_messages"], [1])
        self.assertEqual((out[0]["fact_type"], out[0]["site_text"]), ("symptom", "hai tay"))
        self.assertTrue(out[0]["lesion"] and out[0]["lesion"] != "moi-1")

    def test_failure_returns_empty_after_retry(self):
        out, s = self._run(RuntimeError("boom"), [("PATIENT", "tôi ngứa")])
        self.assertEqual((out, s.calls), ([], 2))


class AfterPlanTest(unittest.TestCase):
    def test_routes_by_queries(self):
        self.assertEqual(_after_plan({"messages": [], "queries": ["vảy nến"]}), "choose_tools")
        self.assertEqual(_after_plan({"messages": [], "queries": []}), "answer")
        self.assertEqual(_after_plan({"messages": []}), "answer")


class DiagPersistTest(unittest.TestCase):
    def test_state_survives_between_turns(self):
        seen: list[dict[str, Any]] = []

        async def step(state: PreDiagnosisState) -> dict[str, Any]:
            seen.append({k: state.get(k) for k in ("facts", "evidence", "done_calls")})
            n = len(state.get("facts", []))
            return {
                "messages": [AIMessage(content="ok")],
                "facts": [*state.get("facts", []), fact(f"f{n}", "x")],
                "evidence": [*state.get("evidence", []), {"id": f"E{n + 1}", "kind": "evidence", "source": "s", "text": "t"}],
                "done_calls": [*state.get("done_calls", []), f"call{n}"],
            }

        fake = StateGraph(PreDiagnosisState)
        fake.add_node("step", step)
        fake.add_edge(START, "step")
        fake.add_edge("step", END)
        ctx = AgentContext(user_id="u", conversation_id="c", message_id="m")

        async def scenario() -> list[Any]:
            with patch.object(settings, "AGENT_TRIAGE_ENABLED", False):
                graph = build_chat_graph(pre_diagnosis=cast(Any, fake.compile()), version="v2")
            cfg = build_run_config("thread-1")
            await graph.ainvoke({"messages": [HumanMessage(content="tôi ngứa")]}, config=cfg, context=ctx)
            await graph.ainvoke({"messages": [HumanMessage(content="ngứa về đêm")]}, config=cfg, context=ctx)
            other = build_run_config("thread-2")
            await graph.ainvoke({"messages": [HumanMessage(content="chào")]}, config=other, context=ctx)
            return seen

        run(scenario())
        self.assertEqual(seen[0], {"facts": None, "evidence": None, "done_calls": None})
        self.assertEqual([f["template_label"] for f in seen[1]["facts"]], ["f0"])
        self.assertEqual(seen[1]["done_calls"], ["call0"])
        self.assertEqual(seen[2]["facts"], None)


class CheckpointerSwapTest(unittest.TestCase):
    def test_checkpointer_assigned_after_compile_is_used(self):
        async def step(state: PreDiagnosisState) -> dict[str, Any]:
            return {"messages": [AIMessage(content="ok")], "facts": [fact("f", "x")]}

        fake = StateGraph(PreDiagnosisState)
        fake.add_node("step", step)
        fake.add_edge(START, "step")
        fake.add_edge("step", END)
        with patch.object(settings, "AGENT_TRIAGE_ENABLED", False):
            graph = build_chat_graph(pre_diagnosis=cast(Any, fake.compile()), version="v2")
        default_saver, swapped = graph.checkpointer, InMemorySaver()
        graph.checkpointer = swapped  # cách worker thay checkpoint RAM bằng Postgres sau khi graph đã biên dịch
        ctx = AgentContext(user_id="u", conversation_id="c")
        cfg = build_run_config("thread-swap")

        async def scenario() -> Any:
            await graph.ainvoke({"messages": [HumanMessage(content="tôi ngứa")]}, config=cfg, context=ctx)
            return await graph.aget_state(cfg)

        state = run(scenario())
        self.assertEqual(state.values["diag"]["facts"][0]["template_label"], "f")
        self.assertIsNotNone(swapped.get_tuple(cfg))
        self.assertIsNone(cast(Any, default_saver).get_tuple(cfg))


if __name__ == "__main__":
    unittest.main()
