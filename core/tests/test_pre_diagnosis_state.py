import asyncio
import unittest
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from agent.common.fact_extractor import ExtractedFact, ExtractedFacts, extract_facts, merge_facts, validate_facts_evidence
from agent.context.agent_context import AgentContext
from agent.graph.chat_graph import build_chat_graph, config_for
from agent.graph.v2.nodes import load_memory_node
from agent.graph.v2.pre_diagnosis_graph import _after_plan
from agent.graph.v2.state import PreDiagState
from agent.middleware.common.model import inject_memory, load_memory
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
        merged = merge_facts([fact("Penicillin", "đang dùng", "medication")], [fact("Penicillin", "dị ứng", "allergy")])
        self.assertEqual(len(merged), 2)

    def test_capped_to_latest(self):
        merged = merge_facts([], [fact(f"f{i}", "x") for i in range(50)])
        self.assertEqual(len(merged), 30)
        self.assertEqual(merged[-1]["template_label"], "f49")

    def test_validate_drops_bad_indices(self):
        out = validate_facts_evidence([{**fact("Ngứa", "tay"), "source_messages": [1, 5, "a"]}], ["ngứa ở tay"])
        self.assertEqual(out[0]["source_messages"], [1])


class ExtractFactsTest(unittest.TestCase):
    def _run(self, result: Any, transcript: list[tuple[str, str]]) -> tuple[list[dict[str, Any]], FakeStructured]:
        structured = FakeStructured(result)
        with patch("agent.common.fact_extractor.get_model", return_value=FakeModel(structured)):
            return run(extract_facts([], transcript)), structured

    def test_skips_llm_without_patient_message(self):
        out, s = self._run(ExtractedFacts(), [("AI", "Chào bạn")])
        self.assertEqual((out, s.calls), ([], 0))

    def test_returns_validated_facts(self):
        result = ExtractedFacts(facts=[ExtractedFact(template_label="Ngứa", fact_type="symptom", detail="hai tay", source_messages=[1, 9])])
        out, _ = self._run(result, [("PATIENT", "tôi ngứa hai tay")])
        self.assertEqual(out[0]["source_messages"], [1])

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

        async def step(state: PreDiagState) -> dict[str, Any]:
            seen.append({k: state.get(k) for k in ("facts", "evidence", "done_calls")})
            n = len(state.get("facts", []))
            return {
                "messages": [AIMessage(content="ok")],
                "facts": [*state.get("facts", []), fact(f"f{n}", "x")],
                "evidence": [*state.get("evidence", []), {"id": f"E{n + 1}", "kind": "evidence", "source": "s", "text": "t"}],
                "done_calls": [*state.get("done_calls", []), f"call{n}"],
            }

        fake = StateGraph(PreDiagState)
        fake.add_node("step", step)
        fake.add_edge(START, "step")
        fake.add_edge("step", END)
        ctx = AgentContext(user_id="u", conversation_id="c", message_id="m")

        async def scenario() -> list[Any]:
            with patch.object(settings, "AGENT_TRIAGE_ENABLED", False):
                graph = build_chat_graph(pre_diagnosis=cast(Any, fake.compile()))
            cfg = config_for("thread-1")
            await graph.ainvoke({"messages": [HumanMessage(content="tôi ngứa")]}, config=cfg, context=ctx)
            await graph.ainvoke({"messages": [HumanMessage(content="ngứa về đêm")]}, config=cfg, context=ctx)
            other = config_for("thread-2")
            await graph.ainvoke({"messages": [HumanMessage(content="chào")]}, config=other, context=ctx)
            return seen

        run(scenario())
        self.assertEqual(seen[0], {"facts": None, "evidence": None, "done_calls": None})
        self.assertEqual([f["template_label"] for f in seen[1]["facts"]], ["f0"])
        self.assertEqual(seen[1]["done_calls"], ["call0"])
        self.assertEqual(seen[2]["facts"], None)


class MemoryInjectedAtFirstNodeTest(unittest.TestCase):
    def _load(self, has: Any, found: list[str]) -> tuple[str, AsyncMock, AsyncMock]:
        has_mock = AsyncMock(side_effect=has) if isinstance(has, Exception) else AsyncMock(return_value=has)
        search_mock = AsyncMock(return_value=found)
        with patch("agent.middleware.common.model.has_memories", has_mock), patch("agent.middleware.common.model.search_memories", search_mock):
            text = run(load_memory([HumanMessage(content="tôi ngứa")], object(), "u"))  # type: ignore[arg-type]
        return text, has_mock, search_mock

    def test_empty_store_skips_embedding(self):
        text, has_mock, search_mock = self._load(False, [])
        self.assertEqual((text, has_mock.await_count, search_mock.await_count), ("", 1, 0))

    def test_non_empty_store_searches_once(self):
        text, _, search_mock = self._load(True, ["dị ứng penicillin", "đang có thai"])
        self.assertEqual(text, "- dị ứng penicillin\n- đang có thai")
        self.assertEqual(search_mock.await_count, 1)

    def test_store_error_gives_empty_text(self):
        text, _, _ = self._load(RuntimeError("down"), [])
        self.assertEqual(text, "")

    def test_inject_memory_is_pure(self):
        self.assertEqual(inject_memory("base", ""), "base")
        self.assertIn("- dị ứng penicillin", inject_memory("base", "- dị ứng penicillin"))

    def test_first_node_loads_and_later_nodes_never_touch_store(self):
        ctx = AgentContext(user_id="u", conversation_id="c")
        load_mock = AsyncMock(return_value="- dị ứng penicillin")
        state: Any = {"messages": [HumanMessage(content="tôi ngứa")]}
        runtime: Any = SimpleNamespace(context=ctx, store=object())
        with patch("agent.graph.v2.nodes.load_memory", load_mock):
            run(load_memory_node(state, runtime))
        self.assertEqual((ctx.memory_text, load_mock.await_count), ("- dị ứng penicillin", 1))
        # các node sau chỉ nối chuỗi trong context
        prompts = [inject_memory(f"base{i}", ctx.memory_text) for i in range(4)]
        self.assertTrue(all("- dị ứng penicillin" in p for p in prompts))
        self.assertEqual(load_mock.await_count, 1)


if __name__ == "__main__":
    unittest.main()
