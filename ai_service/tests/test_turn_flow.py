import asyncio
import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from agent import turn
from agent.context.agent_context import AgentContext
from agent.context.builder import build_context
from agent.dto.schemas import TurnAttachment, TurnRequest
from agent.tools.case_search import search_similar_cases
from app import turn_runner
from main import app as main_app
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
        self.redis, self.clinical, self.consultation = FakeRedis(), AsyncMock(), AsyncMock()
        for target, value in (("get_redis_client", self.redis), ("get_clinical_client", self.clinical), ("get_consultation_client", self.consultation)):
            patcher = patch.object(turn, target, lambda v=value: v)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch("agent.graph.common.get_redis_client", lambda: self.redis)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_done_turn_streams_event_then_saves_clinical_then_replies(self) -> None:
        context = AgentContext(user_id="u", conversation_id="c1", patient_profile_id="pp-1")
        context.turn_facts = [{"template_label": "Ngứa"}]
        asyncio.run(turn.finish_turn(make_request(), {"type": "message.done", "content": "ok"}, content="ok", status="done", context=context))
        self.assertEqual([e[0] for e in self.redis.events], ["conversation:events:c1"] * 2)
        self.assertEqual(self.redis.events[1][1], "[DONE]")
        self.clinical.apply_turn.assert_awaited_once()
        self.assertEqual(self.clinical.apply_turn.await_args.args[0]["patient_profile_id"], "pp-1")
        self.consultation.post_turn_result.assert_awaited_once()
        message_id, body = self.consultation.post_turn_result.await_args.args
        self.assertEqual((message_id, body["status"], body["content"]), ("m1", "done", "ok"))

    def test_clinical_failure_does_not_lose_the_answer(self) -> None:
        self.clinical.apply_turn.side_effect = RuntimeError("clinical chết")
        context = AgentContext(user_id="u", conversation_id="c1")
        context.turn_hypotheses = [{"disease": "x"}]
        with self.assertLogs("agent.turn", level="ERROR"):
            asyncio.run(turn.finish_turn(make_request(), {"type": "message.done"}, content="ok", status="done", context=context))
        self.consultation.post_turn_result.assert_awaited_once()

    def test_question_turn_skips_clinical_when_nothing_to_save(self) -> None:
        asyncio.run(turn.finish_turn(make_request(), {"type": "message.question"}, content="", status="question", choice={"question": "?"}))
        self.clinical.apply_turn.assert_not_awaited()
        self.assertEqual(self.consultation.post_turn_result.await_args.args[1]["choice"], {"question": "?"})


class BuildContextTest(unittest.TestCase):
    def test_pulls_conversation_and_facts_by_id(self) -> None:
        consultation, clinical = AsyncMock(), AsyncMock()
        consultation.get_conversation.return_value = {"user_id": "u1", "patient_profile_id": "pp-1", "model": "gemma4-26b"}
        clinical.get_patient_context.return_value = {"facts": [{"label": "Ngứa", "fact_type": "symptom", "detail": "đêm", "body_site": "tay"}]}
        req = make_request(attached_files=[TurnAttachment(file_name="a.jpg", content_type="image/jpeg", storage_key="k/a.jpg")])
        with patch("agent.context.builder.get_consultation_client", lambda: consultation), patch("agent.context.builder.get_clinical_client", lambda: clinical):
            context = asyncio.run(build_context(req))
        self.assertEqual((context.user_id, context.patient_profile_id, context.image_keys), ("u1", "pp-1", ["k/a.jpg"]))
        self.assertEqual(context.model, settings.AGENT_MODEL_CHOICES["gemma4-26b"])
        self.assertEqual(context.known_facts[0], {"template_label": "Ngứa", "fact_type": "symptom", "detail": "đêm", "body_site": "tay", "source_messages": []})

    def test_missing_conversation_and_clinical_failure_degrade_with_log(self) -> None:
        consultation, clinical = AsyncMock(), AsyncMock()
        consultation.get_conversation.return_value = None
        context = asyncio.run(_build_with(consultation, clinical))
        self.assertEqual((context.user_id, context.known_facts), ("", []))
        consultation.get_conversation.return_value = {"user_id": "u", "patient_profile_id": "pp-1", "model": "x"}
        clinical.get_patient_context.side_effect = RuntimeError("down")
        with self.assertLogs("agent.context.builder", level="WARNING"):
            context = asyncio.run(_build_with(consultation, clinical))
        self.assertEqual(context.known_facts, [])


async def _build_with(consultation: Any, clinical: Any) -> AgentContext:
    with patch("agent.context.builder.get_consultation_client", lambda: consultation), patch("agent.context.builder.get_clinical_client", lambda: clinical):
        return await build_context(make_request())


class CaseSearchTest(unittest.TestCase):
    def test_maps_knowledge_payload_to_case_dict(self) -> None:
        knowledge = AsyncMock()
        knowledge.search_semantic.return_value = [{"case_id": "r1", "diagnosis": "Eczema", "reasoning": "khô da", "instructions": ["bôi kem"], "notes": "n", "images": [{"storage_key": "k"}]}]
        with patch("agent.tools.case_search.get_knowledge_client", lambda: knowledge):
            cases = asyncio.run(search_similar_cases("eczema", 3))
        knowledge.search_semantic.assert_awaited_once_with("eczema", 3, corpus="finalize_report")
        self.assertEqual((cases[0]["doctor_reasoning"], cases[0]["treatment_instructions"], cases[0]["images"]), ("khô da", ["bôi kem"], [{"storage_key": "k"}]))


class TurnRunnerAndApiTest(unittest.TestCase):
    def test_dispatches_by_type_and_cancel_stops_running_turn(self) -> None:
        async def scenario() -> tuple[list[str], bool, bool]:
            calls: list[str] = []
            started = asyncio.Event()

            async def slow_turn(req: TurnRequest) -> None:
                calls.append("turn")
                started.set()
                await asyncio.sleep(30)

            with patch.object(turn_runner, "handle_turn", slow_turn), patch.object(turn_runner, "handle_resume", AsyncMock(side_effect=lambda r: calls.append("resume"))), \
                    patch.object(turn_runner, "handle_consultation_report", AsyncMock(side_effect=lambda r: calls.append("report"))):
                await turn_runner.run_turn(make_request(type="resume", message_id="m2", answer="a"))
                await turn_runner.run_turn(make_request(type="consultation_report", message_id="m3"))
                task = asyncio.create_task(turn_runner.run_turn(make_request(message_id="m1")))
                await started.wait()
                cancelled = turn_runner.cancel_turn("m1")
                await asyncio.sleep(0)
                with self.assertRaises(asyncio.CancelledError):
                    await task
                return calls, cancelled, turn_runner.cancel_turn("m1")

        calls, cancelled, again = asyncio.run(scenario())
        self.assertEqual(calls, ["resume", "report", "turn"])
        self.assertEqual((cancelled, again), (True, False))

    def test_api_requires_internal_key_and_accepts_turn(self) -> None:
        client = TestClient(main_app)  # không vào `with`: không chạy lifespan (Postgres)
        body = make_request().model_dump()
        self.assertEqual(client.post("/internal/turns", json=body).status_code, 403)
        with patch("app.api.internal_api.start_turn") as start:
            r = client.post("/internal/turns", json=body, headers=HEADERS)
        self.assertEqual((r.status_code, r.json()), (202, {"accepted": True}))
        self.assertEqual(start.call_args.args[0].message_id, "m1")
        with patch("app.api.internal_api.cancel_turn", return_value=True):
            self.assertEqual(client.post("/internal/turns/m1/cancel", headers=HEADERS).json(), {"cancelled": True})


if __name__ == "__main__":
    unittest.main()
