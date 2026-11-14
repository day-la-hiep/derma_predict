import asyncio
import unittest
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from app.context.agent_context import AgentContext
from app.graph.v3 import intake as module
from app.state.v3.facts import Fact
from app.tools.v3.extract_slots import Slot
from app.tools.v3.image_analysis import merge_cnn_predictions, parse_image_slots
from app.tools.v3.link_entities import Link
from app.tools.v3.load_history import load_history

NOW = datetime(2026, 11, 14, tzinfo=timezone.utc)
CTX_IMG = AgentContext(user_id="u", conversation_id="c", image_keys=["k1"])


class FakeRuntime:
    def __init__(self, ctx: AgentContext) -> None:
        self.context = ctx


def run_intake(state: dict[str, Any], ctx: AgentContext, slots: list[Slot], links: list[Link], *, image: Any = ([], None),
               cnn: Any = None, history: Any = None) -> tuple[dict[str, Any], dict[str, AsyncMock]]:
    mocks = {
        "extract_slots": AsyncMock(return_value=[s for s in slots if s.source == "text"]),
        "describe_image": AsyncMock(side_effect=image) if isinstance(image, Exception) else AsyncMock(return_value=image),
        "classify_images": AsyncMock(side_effect=cnn) if isinstance(cnn, Exception) else AsyncMock(return_value=cnn or []),
        "_load_history": AsyncMock(return_value=history or []),
        "link_entities": AsyncMock(return_value=links),
        "emit_tool_step": AsyncMock(),
    }
    with patch.multiple(module, **mocks):
        return asyncio.run(module.intake(state, FakeRuntime(ctx))), mocks  # type: ignore[arg-type]


class IntakeTest(unittest.TestCase):
    def test_reads_only_new_messages_and_keeps_absent(self):
        state = {"messages": [HumanMessage(content="cũ", id="m1"), AIMessage(content="hỏi", id="a1"), HumanMessage(content="không sốt", id="m2")], "facts_upto": 2}
        out, mocks = run_intake(state, AgentContext(user_id="u", conversation_id="c"),
                                [Slot(slot="symptom", text="sốt", text_en="fever", assertion="absent")], [Link("effect/phenotype:5", "Fever", 1.0)])
        self.assertEqual(mocks["extract_slots"].call_args.args[1], ["không sốt"])
        fact = Fact.model_validate(out["facts"][0])
        self.assertEqual((fact.assertion, fact.node_id, fact.provenance), ("absent", "effect/phenotype:5", ["m2"]))
        self.assertEqual(out["facts_upto"], 3)
        mocks["_load_history"].assert_not_called()  # không phải lượt đầu
        self.assertNotIn("recent_drugs", out)

    def test_history_loaded_on_first_turn(self):
        history = [{"label": "methotrexate", "object_type": "drug", "kg_node_id": "DB1", "present": True, "kind": "taking", "category": 5}]
        out, mocks = run_intake({"messages": [HumanMessage(content="chào", id="m1")]}, AgentContext(user_id="u", conversation_id="c", patient_profile_id="p1"),
                                [], [], history=history)
        mocks["_load_history"].assert_awaited_once_with("p1")
        self.assertEqual(out["recent_drugs"][0]["drug_id"], "drug:DB1")

    def test_image_slots_linked_together_with_text(self):
        img = Slot(slot="scale", text="vảy", source="image", ref=1)
        out, mocks = run_intake({"messages": [HumanMessage(content="ngứa", id="m1")]}, CTX_IMG,
                                [Slot(slot="symptom", text="ngứa"), img], [Link(None, None, 0.0), Link("effect/phenotype:7", "Scaling skin", 1.0)],
                                image=([img], None))
        self.assertEqual(len(mocks["link_entities"].call_args.args[1]), 2)
        image_fact = next(Fact.model_validate(f) for f in out["facts"] if f["source"] == "image")
        self.assertEqual((image_fact.provenance, image_fact.confidence), (["k1"], 0.6))

    def test_vision_and_cnn_errors_do_not_block_text(self):
        out, _ = run_intake({"messages": [HumanMessage(content="ngứa", id="m1")]}, CTX_IMG,
                            [Slot(slot="symptom", text="ngứa")], [Link(None, None, 0.0)], image=RuntimeError("vlm down"), cnn=RuntimeError("no ckpt"))
        self.assertEqual(len(out["facts"]), 1)
        self.assertNotIn("cnn_scores", out)

    def test_poor_image_reported(self):
        out, _ = run_intake({"messages": [HumanMessage(content="ngứa", id="m1")]}, CTX_IMG, [], [], image=([], "model ảnh báo ảnh không nhận định được"))
        self.assertEqual(out["image_issues"], ["ảnh 1: model ảnh báo ảnh không nhận định được"])

    def test_conflict_opposite_assertion(self):
        slots = [Slot(slot="scale", text="vảy", assertion="absent"), Slot(slot="scale", text="vảy", source="image", ref=1)]
        link = Link("effect/phenotype:7", "Scaling skin", 1.0)
        out, _ = run_intake({"messages": [HumanMessage(content="không có vảy", id="m1")]}, CTX_IMG, slots, [link, link], image=([slots[1]], None))
        facts = [Fact.model_validate(x) for x in out["facts"]]
        self.assertEqual([(f.source, f.conflict) for f in facts], [("text", True)])

    def test_conflict_same_slot_different_node(self):
        slots = [Slot(slot="color", text="đỏ"), Slot(slot="color", text="tím", source="image", ref=1)]
        out, _ = run_intake({"messages": [HumanMessage(content="mảng đỏ", id="m1")]}, CTX_IMG, slots,
                            [Link("effect/phenotype:1", "Erythema", 1.0), Link("effect/phenotype:2", "Purpura", 1.0)], image=([slots[1]], None))
        self.assertTrue(all(Fact.model_validate(f).conflict for f in out["facts"]))

    def test_ambiguous_link_recorded(self):
        out, _ = run_intake({"messages": [HumanMessage(content="nổi bọng", id="m1")]}, AgentContext(user_id="u", conversation_id="c"),
                            [Slot(slot="morphology", text="bọng")], [Link("effect/phenotype:3", "Bulla", 0.8, ambiguous=True)])
        self.assertEqual(out["ambiguous"][0]["node_id"], "effect/phenotype:3")


class HelpersTest(unittest.TestCase):
    def test_merge_cnn_takes_max_and_maps(self):
        out = merge_cnn_predictions([{"top": [{"disease": "Psoriasis", "confidence": 0.4}]},
                                     {"top": [{"disease": "Psoriasis", "confidence": 0.7}, {"disease": "Vitiligo", "confidence": 0.2}]}, None])
        self.assertEqual(out[0], {"label": "Psoriasis", "prob": 0.7, "disease_id": "disease:5083"})
        self.assertIsNone(out[1]["disease_id"])

    def test_parse_image_slots_from_text_with_noise(self):
        text = 'Đây: ```json\n{"items": [{"slot": "scale", "text": "vảy trắng", "text_en": "scaling", "assertion": "present"},' \
               ' {"slot": "symptom", "text": "ngứa", "assertion": "present"}], "quality": "ok"}\n```'
        slots, quality = parse_image_slots(text)
        self.assertEqual(([s.slot for s in slots], quality), (["scale"], "ok"))  # symptom không nhìn thấy được trên ảnh → bỏ
        with self.assertRaises(ValueError):
            parse_image_slots("không có json")

    def test_load_history_from_graph_facts(self):
        known = [
            {"id": "f1", "label": "vảy nến", "object_type": "disease", "kg_node_id": "5083", "present": True, "category": 5, "observed_at": "2025-11-14T00:00:00"},
            {"label": "methotrexate", "object_type": "drug", "kg_node_id": "DB1", "present": True, "kind": "taking", "category": 5},
            {"label": "penicillin", "object_type": "drug", "kg_node_id": "DB2", "present": True, "kind": "allergy", "category": 5},
            {"label": "ngứa", "object_type": "effect/phenotype", "kg_node_id": None, "present": False, "category": 1},
        ]
        facts, diseases, drugs = load_history(known, NOW)
        self.assertEqual((diseases[0]["disease_id"], facts[0].time.year, facts[0].provenance), ("disease:5083", 2025, ["f1"]))
        self.assertEqual([d["name"] for d in drugs], ["methotrexate"])
        self.assertEqual(facts[3].assertion, "absent")


if __name__ == "__main__":
    unittest.main()
