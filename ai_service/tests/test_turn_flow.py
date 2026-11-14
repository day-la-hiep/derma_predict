import asyncio
import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import turn
from app.context.agent_context import AgentContext
from app.context.turn_context_builder import build_context
from app.dto.turn_request import TurnAttachment, TurnRequest
from app.tools.similar_case_search import search_similar_cases
from app import api as turn_runner
from app.main import app as main_app
from app.config.settings import settings

HEADERS = {"X-Internal-Key": settings.INTERNAL_API_KEY}


def make_request(**overrides: Any) -> TurnRequest:
    data: dict[str, Any] = {"type": "turn", "conversation_id": "c1", "message_id": "m1", "content": "tôi bị ngứa"}
    data.update(overrides)
    return TurnRequest.model_validate(data)


class FakeRedis:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    async def add_stream_event(self, stream: str, event: str, **_: Any) -> str:
        self.events.append((stream, event))
        return "1-0"


class FinishTurnTest(unittest.TestCase):
    def setUp(self) -> None:
        self.redis, self.clinical, self.consultation, self.knowledge = FakeRedis(), AsyncMock(), AsyncMock(), AsyncMock()
        self.knowledge.apply_patient_facts.return_value = {"applied": 1, "skipped": [], "lesions": []}
        for target, value in (
            ("get_redis_client", self.redis), ("get_clinical_client", self.clinical), ("get_consultation_client", self.consultation),
        ):
            patcher = patch.object(turn, target, lambda v=value: v)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch("app.reasoning.patient_fact_store.get_knowledge_client", lambda: self.knowledge)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch("app.middleware.tool_step_events.get_redis_client", lambda: self.redis)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_done_turn_streams_event_then_saves_clinical_then_replies(self) -> None:
        context = AgentContext(user_id="u", conversation_id="c1", patient_profile_id="pp-1")
        context.turn_hypotheses = [{"disease": "x"}]
        asyncio.run(turn.finish_turn(make_request(), {"type": "message.done", "content": "ok"}, content="ok", context=context))
        self.assertEqual([e[0] for e in self.redis.events], ["conversation:events:c1"] * 2)
        self.assertEqual(self.redis.events[1][1], "[DONE]")
        self.clinical.apply_turn.assert_awaited_once()
        body = self.clinical.apply_turn.await_args.args[0]
        self.assertEqual(body["patient_profile_id"], "pp-1")
        self.assertNotIn("facts", body)
        self.knowledge.apply_patient_facts.assert_not_awaited()
        self.consultation.post_turn_result.assert_awaited_once()
        message_id, body = self.consultation.post_turn_result.await_args.args
        self.assertEqual((message_id, body["status"], body["content"]), ("m1", "done", "ok"))

    def test_facts_go_to_knowledge_not_clinical(self) -> None:
        context = AgentContext(user_id="u", conversation_id="c1", patient_profile_id="pp-1")
        context.turn_facts = [{"template_label": "ngứa", "category": 1, "lesion": "L1", "site_text": "tay", "source_messages": ["m0"], "detail": "đêm"}]
        asyncio.run(turn.finish_turn(make_request(), {"type": "message.done"}, content="ok", context=context))
        self.clinical.apply_turn.assert_not_awaited()
        profile_id, facts = self.knowledge.apply_patient_facts.await_args.args
        self.assertEqual(profile_id, "pp-1")
        self.assertEqual((facts[0]["category"], facts[0]["lesion_id"], facts[0]["source_message_id"], facts[0]["label"]), (1, "L1", "m0", "ngứa"))
        self.assertTrue(facts[0]["observed_at"])

    def test_knowledge_failure_or_skipped_facts_are_logged_and_answer_kept(self) -> None:
        context = AgentContext(user_id="u", conversation_id="c1", patient_profile_id="pp-1")
        context.turn_facts = [{"template_label": "ngứa", "category": 1}]
        self.knowledge.apply_patient_facts.side_effect = RuntimeError("knowledge chết")
        with self.assertLogs("app.reasoning.patient_fact_store", level="ERROR"):
            asyncio.run(turn.finish_turn(make_request(), {"type": "message.done"}, content="ok", context=context))
        self.consultation.post_turn_result.assert_awaited_once()
        self.assertFalse(context.turn_facts_saved)  # lỗi thì chưa tính là đã ghi
        self.knowledge.apply_patient_facts.side_effect = None
        self.knowledge.apply_patient_facts.return_value = {"applied": 0, "skipped": [{"index": 0, "reason": "thiếu tổn thương"}], "lesions": []}
        with self.assertLogs("app.reasoning.patient_fact_store", level="WARNING") as logs:
            asyncio.run(turn.finish_turn(make_request(), {"type": "message.done"}, content="ok", context=context))
        self.assertIn("thiếu tổn thương", logs.output[0])

    def test_facts_already_saved_by_a_tool_are_not_written_again(self) -> None:
        context = AgentContext(user_id="u", conversation_id="c1", patient_profile_id="pp-1")
        context.turn_facts = [{"template_label": "ngứa", "category": 1}]
        context.turn_facts_saved = True
        asyncio.run(turn.finish_turn(make_request(), {"type": "message.done"}, content="ok", context=context))
        self.knowledge.apply_patient_facts.assert_not_awaited()

    def test_no_profile_means_no_fact_write(self) -> None:
        context = AgentContext(user_id="u", conversation_id="c1")
        context.turn_facts = [{"template_label": "ngứa", "category": 1}]
        asyncio.run(turn.finish_turn(make_request(), {"type": "message.done"}, content="ok", context=context))
        self.knowledge.apply_patient_facts.assert_not_awaited()

    def test_clinical_failure_does_not_lose_the_answer(self) -> None:
        self.clinical.apply_turn.side_effect = RuntimeError("clinical chết")
        context = AgentContext(user_id="u", conversation_id="c1")
        context.turn_hypotheses = [{"disease": "x"}]
        with self.assertLogs("app.turn", level="ERROR"):
            asyncio.run(turn.finish_turn(make_request(), {"type": "message.done"}, content="ok", context=context))
        self.consultation.post_turn_result.assert_awaited_once()


class BuildContextTest(unittest.TestCase):
    def test_pulls_conversation_and_facts_by_id(self) -> None:
        consultation, knowledge = AsyncMock(), AsyncMock()
        consultation.get_conversation.return_value = {"user_id": "u1", "patient_profile_id": "pp-1", "model": "gemma4-26b"}
        knowledge.get_patient_facts.return_value = {
            "lesions": [{"id": "L1", "site_text": "tay", "scope": "skin"}],
            "facts": [{"lesion_id": None, "category": 5, "relation": "PT_TAKES_DRUG", "label": "penicillin", "detail": "nổi mề đay", "object_type": "drug",
                       "kg_node_id": None, "present": True, "status": "current", "name": "", "kind": "allergy", "effect": "", "of": "", "onset_text": "",
                       "source_message_id": None, "link_method": "none"},
                      {"lesion_id": "L1", "category": 1, "relation": "PT_HAS_SYMPTOM", "label": "Ngứa", "detail": "đêm", "object_type": "effect/phenotype",
                       "kg_node_id": "989", "present": True, "status": "current", "name": "", "kind": "", "effect": "", "of": "", "onset_text": "",
                       "source_message_id": None, "link_method": "llm"}],
        }
        req = make_request(attached_files=[TurnAttachment(file_name="a.jpg", content_type="image/jpeg", storage_key="k/a.jpg")])
        with patch("app.context.turn_context_builder.get_consultation_client", lambda: consultation), patch("app.context.turn_context_builder.get_knowledge_client", lambda: knowledge):
            context = asyncio.run(build_context(req))
        self.assertEqual((context.user_id, context.patient_profile_id, context.image_keys), ("u1", "pp-1", ["k/a.jpg"]))
        self.assertEqual(context.model, settings.AGENT_MODEL_CHOICES["gemma4-26b"])
        self.assertEqual(context.known_lesions, [{"id": "L1", "site_text": "tay", "scope": "skin"}])
        by_label = {f["template_label"]: f for f in context.known_facts}
        fact = by_label["Ngứa"]
        self.assertEqual((fact["template_label"], fact["fact_type"], fact["category"], fact["lesion"], fact["site_text"], fact["kg_node_id"]), ("Ngứa", "symptom", 1, "L1", "tay", "989"))
        allergy = by_label["penicillin"]  # dị ứng nhập ở form hồ sơ cũng nằm trong graph nên đến agent qua cùng một đường đọc
        self.assertEqual((allergy["category"], allergy["object_type"], allergy["kind"], allergy["detail"], allergy["fact_type"]), (5, "drug", "allergy", "nổi mề đay", "allergy"))

    def test_missing_conversation_and_knowledge_failure_degrade_with_log(self) -> None:
        consultation, knowledge = AsyncMock(), AsyncMock()
        consultation.get_conversation.return_value = None
        context = asyncio.run(_build_with(consultation, knowledge))
        self.assertEqual((context.user_id, context.known_facts), ("", []))
        consultation.get_conversation.return_value = {"user_id": "u", "patient_profile_id": "pp-1", "model": "x"}
        knowledge.get_patient_facts.side_effect = RuntimeError("down")
        with self.assertLogs("app.context.turn_context_builder", level="WARNING"):
            context = asyncio.run(_build_with(consultation, knowledge))
        self.assertEqual((context.known_facts, context.known_lesions), ([], []))


async def _build_with(consultation: Any, knowledge: Any) -> AgentContext:
    with patch("app.context.turn_context_builder.get_consultation_client", lambda: consultation), patch("app.context.turn_context_builder.get_knowledge_client", lambda: knowledge):
        return await build_context(make_request())


class CaseSearchTest(unittest.TestCase):
    def test_maps_knowledge_payload_to_case_dict(self) -> None:
        knowledge = AsyncMock()
        knowledge.search_semantic.return_value = [{"case_id": "r1", "diagnosis": "Eczema", "reasoning": "khô da", "instructions": ["bôi kem"], "notes": "n", "images": [{"storage_key": "k"}]}]
        with patch("app.tools.similar_case_search.get_knowledge_client", lambda: knowledge):
            cases = asyncio.run(search_similar_cases("eczema", 3))
        knowledge.search_semantic.assert_awaited_once_with("eczema", 3, corpus="finalize_report")
        self.assertEqual((cases[0]["doctor_reasoning"], cases[0]["treatment_instructions"], cases[0]["images"]), ("khô da", ["bôi kem"], [{"storage_key": "k"}]))


class TurnRunnerAndApiTest(unittest.TestCase):
    def test_cancel_stops_running_turn(self) -> None:
        async def scenario() -> tuple[list[str], bool, bool]:
            calls: list[str] = []
            started = asyncio.Event()

            async def slow_turn(req: TurnRequest) -> None:
                calls.append("turn")
                started.set()
                await asyncio.sleep(30)

            with patch.object(turn_runner, "handle_turn", slow_turn):
                task = asyncio.create_task(turn_runner.run_turn(make_request(message_id="m1")))
                await started.wait()
                cancelled = turn_runner.cancel_turn("m1")
                await asyncio.sleep(0)
                with self.assertRaises(asyncio.CancelledError):
                    await task
                return calls, cancelled, turn_runner.cancel_turn("m1")

        calls, cancelled, again = asyncio.run(scenario())
        self.assertEqual(calls, ["turn"])
        self.assertEqual((cancelled, again), (True, False))

    def test_api_requires_internal_key_and_accepts_turn(self) -> None:
        client = TestClient(main_app)  # không vào `with`: không chạy lifespan (Postgres)
        body = make_request().model_dump()
        self.assertEqual(client.post("/internal/turns", json=body).status_code, 403)
        with patch("app.api.start_turn") as start:
            r = client.post("/internal/turns", json=body, headers=HEADERS)
        self.assertEqual((r.status_code, r.json()), (202, {"accepted": True}))
        self.assertEqual(start.call_args.args[0].message_id, "m1")
        with patch("app.api.cancel_turn", return_value=True):
            self.assertEqual(client.post("/internal/turns/m1/cancel", headers=HEADERS).json(), {"cancelled": True})


if __name__ == "__main__":
    unittest.main()
