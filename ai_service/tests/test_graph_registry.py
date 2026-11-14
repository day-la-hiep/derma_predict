import asyncio
import unittest
from typing import Any
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from app.common.tracing import build_run_config
from app.config.settings import settings
from app.context.agent_context import AgentContext
from app.graph.chat_graph import _load_diag, build_chat_graph
from app.graph.registry import get_pre_diagnosis
from app.state.v3.pre_diagnosis_state import PreDiagnosisState


class RegistryTest(unittest.TestCase):
    def test_unknown_version_raises(self):
        with self.assertRaises(ValueError):
            get_pre_diagnosis("v9")

    def test_both_versions_build(self):
        for version in ("v2", "v3"):
            with patch.object(settings, "AGENT_TRIAGE_ENABLED", False):
                self.assertIsNotNone(build_chat_graph(version=version))

    def test_default_is_v3(self):
        self.assertEqual(settings.AGENT_PRE_DIAGNOSIS_VERSION, "v3")


class LoadDiagTest(unittest.TestCase):
    def test_same_version_kept_without_version_key(self):
        self.assertEqual(_load_diag({"version": "v3", "facts": [1]}, "v3"), {"facts": [1]})

    def test_other_version_dropped(self):
        self.assertEqual(_load_diag({"version": "v2", "facts": [1]}, "v3"), {})

    def test_missing_version_means_v2(self):
        self.assertEqual(_load_diag({"facts": [1]}, "v3"), {})
        self.assertEqual(_load_diag({"facts": [1]}, "v2"), {"facts": [1]})


class DiagVersionPersistTest(unittest.TestCase):
    def test_diag_saved_with_version_and_reloaded(self):
        seen: list[Any] = []

        async def step(state: PreDiagnosisState) -> dict[str, Any]:
            seen.append(state.get("asked"))
            return {"messages": [AIMessage(content="ok")], "asked": [*state.get("asked", []), "p"]}

        fake = StateGraph(PreDiagnosisState)
        fake.add_node("step", step)
        fake.add_edge(START, "step")
        fake.add_edge("step", END)
        ctx = AgentContext(user_id="u", conversation_id="c")

        async def scenario() -> Any:
            with patch.object(settings, "AGENT_TRIAGE_ENABLED", False):
                graph = build_chat_graph(pre_diagnosis=fake.compile(), version="v3")  # pyright: ignore[reportArgumentType]
            cfg = build_run_config("thread-v3")
            await graph.ainvoke({"messages": [HumanMessage(content="a")]}, config=cfg, context=ctx)
            await graph.ainvoke({"messages": [HumanMessage(content="b")]}, config=cfg, context=ctx)
            return await graph.aget_state(cfg)

        state = asyncio.run(scenario())
        self.assertEqual(seen, [None, ["p"]])
        self.assertEqual(state.values["diag"], {"version": "v3", "asked": ["p", "p"]})


if __name__ == "__main__":
    unittest.main()
