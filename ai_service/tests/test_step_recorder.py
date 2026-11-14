import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from app.common.tracing import build_run_config
from app.config.settings import settings
from app.context.agent_context import AgentContext
from app.graph.chat_graph import build_chat_graph
from app.state.v3.pre_diagnosis_state import PreDiagnosisState


async def step(state: PreDiagnosisState) -> dict[str, Any]:
    return {"messages": [AIMessage(content="ok")], "asked": ["p"]}


def run_turn(conversation_id: str) -> None:
    fake = StateGraph(PreDiagnosisState)
    fake.add_node("step", step)
    fake.add_edge(START, "step")
    fake.add_edge("step", END)
    with patch.object(settings, "AGENT_TRIAGE_ENABLED", False):
        graph = build_chat_graph(pre_diagnosis=fake.compile(), version="v3")  # pyright: ignore[reportArgumentType]
    ctx = AgentContext(user_id="u", conversation_id=conversation_id)
    asyncio.run(graph.ainvoke({"messages": [HumanMessage(content="a")]}, config=build_run_config(conversation_id), context=ctx))


class StepRecorderTest(unittest.TestCase):
    def test_writes_one_line_per_node_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(settings, "AGENT_STEP_LOG_DIR", tmp):
                run_turn("conv-1")
            lines = [json.loads(x) for x in (Path(tmp) / "conv-1.jsonl").read_text(encoding="utf-8").splitlines()]
        nodes = [r["node"] for r in lines]
        self.assertIn("step", nodes)
        self.assertIn("pre_diagnosis", nodes)
        rec = next(r for r in lines if r["node"] == "step")
        self.assertIn("asked", rec["output_keys"])
        self.assertIsNone(rec["error"])

    def test_disabled_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(settings, "AGENT_STEP_LOG_DIR", ""):
                run_turn("conv-2")
            self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
