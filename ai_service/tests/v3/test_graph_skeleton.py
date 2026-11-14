import asyncio
import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage

from app.common.tracing import build_run_config
from app.config.settings import settings
from app.context.agent_context import AgentContext
from app.graph.chat_graph import build_chat_graph


class SkeletonTest(unittest.TestCase):
    def test_v3_answers_and_saves_versioned_diag(self):
        model = FakeListChatModel(responses=["Chào bạn. Thông tin trên chỉ mang tính tham khảo, không phải chẩn đoán y khoa."])
        ctx = AgentContext(user_id="u", conversation_id="")  # rỗng: emit_tool_step không publish lên Redis

        async def scenario() -> Any:
            with patch.object(settings, "AGENT_TRIAGE_ENABLED", False):
                graph = build_chat_graph(version="v3")
            cfg = build_run_config("thread-skeleton")
            with patch("app.graph.v3.conclude.get_model_for_turn", return_value=model), \
                    patch("app.graph.v3.intake.extract_slots", AsyncMock(return_value=[])):
                await graph.ainvoke({"messages": [HumanMessage(content="tôi bị ngứa")]}, config=cfg, context=ctx)
            return await graph.aget_state(cfg)

        state = asyncio.run(scenario())
        last = state.values["messages"][-1]
        self.assertIsInstance(last, AIMessage)
        self.assertIn("không phải chẩn đoán y khoa", last.text)
        self.assertEqual(state.values["diag"]["version"], "v3")
        self.assertEqual(state.values["diag"]["facts_upto"], 1)
        self.assertEqual(state.values["diag"]["ranking"], [])  # chưa có bằng chứng: phần cho bác sĩ rỗng, vẫn trả lời


    def test_v3_ask_branch_records_question(self):
        model = FakeListChatModel(responses=["Bạn có sốt không? Thông tin trên chỉ mang tính tham khảo, không phải chẩn đoán y khoa."])
        ctx = AgentContext(user_id="u", conversation_id="")  # rỗng: emit_tool_step không publish lên Redis
        question = {"node_id": "effect/phenotype:1945", "text": "Fever", "kind": "discriminate"}

        async def scenario() -> Any:
            with patch.object(settings, "AGENT_TRIAGE_ENABLED", False):
                graph = build_chat_graph(version="v3")
            cfg = build_run_config("thread-ask")
            with patch("app.graph.v3.conclude.get_model_for_turn", return_value=model), \
                    patch("app.graph.v3.intake.extract_slots", AsyncMock(return_value=[])), \
                    patch("app.graph.v3.check.select_discriminator", AsyncMock(return_value=question)), \
                    patch("app.graph.v3.check.should_stop", return_value=(False, "cần hỏi")):
                await graph.ainvoke({"messages": [HumanMessage(content="tôi bị ngứa")]}, config=cfg, context=ctx)
            return await graph.aget_state(cfg)

        diag = asyncio.run(scenario()).values["diag"]
        self.assertEqual((diag["asked"], diag["rounds"]), (["effect/phenotype:1945"], 1))


if __name__ == "__main__":
    unittest.main()
