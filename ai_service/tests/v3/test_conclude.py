import asyncio
import unittest
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from app.context.agent_context import AgentContext
from app.graph.v3 import ask as ask_module
from app.graph.v3 import conclude as conclude_module
from app.state.v3.diagnosis import EvidenceRow, GuidelineNote, Hypothesis
from app.tools.v3.phrase_question import build_ask_prompt
from app.tools.v3.reason_cot import DiseaseReasoning, Reasoning
from app.tools.v3.verify_claims import verify_claims
from app.tools.v3.write_report import build_ranking, build_turn_hypotheses

NOW = datetime(2026, 11, 14, tzinfo=timezone.utc)
PSO = "disease:5083"
ROW = EvidenceRow(disease_id=PSO, matched=["effect/phenotype:40189"], missing=["effect/phenotype:600"],
                  guideline=[GuidelineNote(fact="Scaling skin", stance="support", chunk_id="c1", quote="silvery scale")],
                  names={"effect/phenotype:40189": "Scaling skin", "effect/phenotype:600": "Nail pitting"})
HYPS = [Hypothesis(disease_id=PSO, name="psoriasis", score=0.6), Hypothesis(disease_id="disease:2", name="eczema", score=0.4)]


class FakeRuntime:
    def __init__(self, ctx: AgentContext) -> None:
        self.context = ctx


def ctx(**kw: Any) -> AgentContext:
    return AgentContext(user_id="u", conversation_id="", **kw)  # rỗng: không publish Redis


class VerifyClaimsTest(unittest.TestCase):
    def test_bad_cites_unverified_and_disease_dropped(self):
        reasoning = Reasoning(per_disease=[
            DiseaseReasoning(disease_id=PSO, summary="khớp vảy", guideline_view="sách ủng hộ", cites=["effect/phenotype:40189", "c1", "c999"]),
            DiseaseReasoning(disease_id="disease:2", summary="không rõ", cites=["c1"]),  # c1 không thuộc bảng của bệnh này
            DiseaseReasoning(disease_id="disease:9", summary="ngoài bảng", cites=[]),
        ])
        rows = [ROW, EvidenceRow(disease_id="disease:2")]
        kept, claims = verify_claims(reasoning, rows)
        self.assertEqual([(k.disease_id, k.cites) for k in kept], [(PSO, ["effect/phenotype:40189", "c1"])])
        self.assertEqual([c.status for c in claims], ["verified", "verified", "unverified"])


class ReportTest(unittest.TestCase):
    def test_turn_hypotheses_match_clinical_format(self):
        ranked = [DiseaseReasoning(disease_id=PSO, confidence="vừa", body_site="tay", cites=["effect/phenotype:40189", "c1"])]
        out = build_turn_hypotheses(ranked, HYPS, [ROW])[0]
        self.assertEqual({k: out[k] for k in ("disease", "code", "body_site", "confidence", "missing")},
                         {"disease": "psoriasis", "code": "Psoriasis", "body_site": "tay", "confidence": "vừa", "missing": ["Nail pitting"]})
        self.assertEqual([e["source"] for e in out["evidence"]], ["đồ thị tri thức", "sách"])
        self.assertEqual(build_ranking(ranked, HYPS)[0]["score"], 0.6)

    def test_unknown_body_site_left_empty(self):
        out = build_turn_hypotheses([DiseaseReasoning(disease_id=PSO, body_site="khuỷu tay", cites=["c1"])], HYPS, [ROW])[0]
        self.assertEqual(out["body_site"], "")


class ReasonNodeTest(unittest.TestCase):
    def test_reason_failure_still_returns_empty_ranking(self):
        state: dict[str, Any] = {"messages": [], "hypotheses": [h.model_dump() for h in HYPS], "evidence": [ROW.model_dump()]}
        c = ctx()
        with patch.object(conclude_module, "reason_cot", AsyncMock(side_effect=RuntimeError("model không trả Reasoning"))):
            out = asyncio.run(conclude_module.reason(state, FakeRuntime(c)))  # type: ignore[arg-type]
        self.assertEqual((out["ranking"], c.turn_hypotheses), ([], []))

    def test_reason_retries_once_when_all_cites_invalid(self):
        state: dict[str, Any] = {"messages": [], "hypotheses": [h.model_dump() for h in HYPS], "evidence": [ROW.model_dump()]}
        bad = Reasoning(per_disease=[DiseaseReasoning(disease_id=PSO, summary="x", cites=["E1"])])
        good = Reasoning(per_disease=[DiseaseReasoning(disease_id=PSO, summary="x", cites=["c1"])])
        llm = AsyncMock(side_effect=[bad, good])
        with patch.object(conclude_module, "reason_cot", llm):
            out = asyncio.run(conclude_module.reason(state, FakeRuntime(ctx())))  # type: ignore[arg-type]
        self.assertEqual((llm.await_count, out["ranking"][0]["disease_id"]), (2, PSO))
        self.assertIn("CHỈ chép", llm.call_args.kwargs["retry_hint"])

    def test_answer_context_has_red_flags_and_no_disease_names(self):
        state: dict[str, Any] = {"messages": [], "urgency": "urgent", "red_flags": ["nghi SJS/TEN: recent_drug + fever + mucosal"],
                                 "ranking": [{"disease_id": PSO, "name": "psoriasis"}], "facts": []}
        text = conclude_module.build_answer_context(state)  # type: ignore[arg-type]
        self.assertIn("KHẨN CẤP", text)
        self.assertIn("nghi SJS/TEN", text)
        self.assertNotIn("psoriasis", text)
        self.assertIn("(chưa rõ)", text)


class AskNodeTest(unittest.TestCase):
    def run_ask(self, state: dict[str, Any], c: AgentContext, seen: str = "unclear", next_q: dict[str, Any] | None = None) -> tuple[dict[str, Any], AsyncMock]:
        llm = AsyncMock(return_value={"messages": [AIMessage(content="Bạn có sốt không?")]})
        with patch.object(ask_module, "reply", llm), patch.object(ask_module, "vlm_verify", AsyncMock(return_value=seen)), \
                patch.object(ask_module, "select_discriminator", AsyncMock(return_value=next_q)):
            return asyncio.run(ask_module.ask(state, FakeRuntime(c))), llm  # type: ignore[arg-type]

    def test_no_image_asks_patient_and_records(self):
        q = {"node_id": "effect/phenotype:1945", "text": "Fever", "kind": "discriminate"}
        out, llm = self.run_ask({"messages": [HumanMessage(content="ngứa")], "question": q, "asked": ["x"], "rounds": 1}, ctx())
        self.assertEqual((out["asked"], out["rounds"]), (["x", "effect/phenotype:1945"], 2))
        self.assertIn("Fever", llm.call_args.args[2])
        self.assertNotIn("facts", out)

    def test_image_answers_then_next_question(self):
        q = {"node_id": "effect/phenotype:40189", "text": "Scaling skin", "kind": "discriminate"}
        nxt = {"node_id": "effect/phenotype:1945", "text": "Fever", "kind": "discriminate"}
        out, llm = self.run_ask({"messages": [HumanMessage(content="ngứa")], "question": q}, ctx(image_keys=["k1"]), seen="yes", next_q=nxt)
        self.assertEqual(out["asked"], ["effect/phenotype:40189", "effect/phenotype:1945"])
        self.assertEqual((out["facts"][0]["source"], out["facts"][0]["assertion"]), ("image", "present"))
        self.assertIn("Fever", llm.call_args.args[2])

    def test_conflict_question_not_sent_to_image(self):
        q = {"node_id": "conflict:color:x", "text": "color: đỏ", "kind": "conflict"}
        out, _ = self.run_ask({"messages": [], "question": q}, ctx(image_keys=["k1"]), seen="yes")
        self.assertNotIn("facts", out)


class AskPromptTest(unittest.TestCase):
    def test_image_issue_reminder(self):
        text = build_ask_prompt(None, ["ảnh 1: ảnh mờ (độ nét 3)"])
        self.assertIn("gửi lại ảnh", text)
        self.assertIn("diễn biến", text)


if __name__ == "__main__":
    unittest.main()
