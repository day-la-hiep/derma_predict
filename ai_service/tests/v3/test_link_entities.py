import asyncio
import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from app.context.agent_context import AgentContext
from app.tools.v3 import link_entities as module
from app.tools.v3.extract_slots import Slot
from app.tools.v3.link_entities import LinkChoice, LinkChoices, decide_link, link_entities

CTX = AgentContext(user_id="u", conversation_id="c")
CANDS = [{"id": "10", "name": "Skin vesicle", "score": 0.55}, {"id": "11", "name": "Vesicular rash", "score": 0.3}]
CLOSE = [{"id": "10", "name": "Bulla", "score": 0.5}, {"id": "11", "name": "Bullae", "score": 0.45}]


class FakeKnowledge:
    def __init__(self, by_type: dict[str, list[dict[str, Any]]]) -> None:
        self.by_type = by_type
        self.calls: list[list[dict[str, str]]] = []

    async def get_link_candidates(self, mentions: list[dict[str, str]], limit: int = 6) -> list[dict[str, Any]]:
        self.calls.append(mentions)
        return [self.by_type[m["object_type"]].pop(0) for m in mentions]


def loose(cands: list[dict[str, Any]]) -> dict[str, Any]:
    return {"exact": None, "candidates": cands, "xref": None}


def exact(id_: str, name: str, xref: dict[str, str] | None = None) -> dict[str, Any]:
    hit = {"id": id_, "name": name, "score": 1.0}
    return {"exact": hit, "candidates": [hit], "xref": xref}


def run(slots: list[Slot], kc: FakeKnowledge, choices: LinkChoices | Exception | None = None) -> list[module.Link]:
    module._cache.clear()
    llm = AsyncMock(side_effect=choices) if isinstance(choices, Exception) else AsyncMock(return_value=choices)
    with patch.object(module, "get_knowledge_client", return_value=kc), patch.object(module, "invoke_structured_with_retry", llm):
        return asyncio.run(link_entities(CTX, slots))


class DecideLinkTest(unittest.TestCase):
    def test_accept_above_threshold(self):
        link = decide_link(CANDS, "effect/phenotype", "10", 0.9)
        self.assertEqual((link.node_id, link.ambiguous), ("effect/phenotype:10", False))

    def test_below_threshold_is_nil(self):
        self.assertIsNone(decide_link(CANDS, "effect/phenotype", "10", 0.6).node_id)

    def test_close_top_scores_ambiguous(self):
        link = decide_link(CLOSE, "effect/phenotype", "11", 0.8)
        self.assertEqual((link.node_id, link.ambiguous), ("effect/phenotype:11", True))

    def test_id_outside_list_is_nil(self):
        self.assertIsNone(decide_link(CANDS, "effect/phenotype", "999", 0.95).node_id)
        self.assertIsNone(decide_link(CANDS, "effect/phenotype", None, 0.95).node_id)


class LinkEntitiesTest(unittest.TestCase):
    def test_exact_needs_no_llm_and_location_not_linked(self):
        kc = FakeKnowledge({"effect/phenotype": [exact("1", "Pruritus")]})
        links = run([Slot(slot="symptom", text="ngứa", text_en="pruritus"), Slot(slot="location", text="khuỷu tay")], kc)
        self.assertEqual(links[0].node_id, "effect/phenotype:1")
        self.assertIsNone(links[1].node_id)
        self.assertEqual(len(kc.calls), 1)

    def test_llm_chooses_by_candidate_id(self):
        kc = FakeKnowledge({"effect/phenotype": [loose(CANDS)]})
        choice = LinkChoices(items=[LinkChoice(mention_index=1, candidate_id="10", confidence=0.8)])
        links = run([Slot(slot="morphology", text="mụn nước", text_en="vesicle")], kc, choice)
        self.assertEqual((links[0].node_id, links[0].node_name), ("effect/phenotype:10", "Skin vesicle"))

    def test_dermo_fallback_uses_hpo_xref(self):
        xref = {"type": "effect/phenotype", "id": "11138", "name": "Plaque"}
        kc = FakeKnowledge({"effect/phenotype": [loose([])], "dermo": [exact("DERMO:1", "plaque", xref)]})
        links = run([Slot(slot="morphology", text="mảng", text_en="plaque")], kc)
        self.assertEqual(links[0].node_id, "effect/phenotype:11138")

    def test_dermo_without_xref_kept_as_dermo(self):
        kc = FakeKnowledge({"effect/phenotype": [loose([])], "dermo": [exact("DERMO:1", "plaque")]})
        self.assertEqual(run([Slot(slot="morphology", text="mảng")], kc)[0].node_id, "dermo:DERMO:1")

    def test_llm_error_keeps_text(self):
        kc = FakeKnowledge({"effect/phenotype": [loose(CANDS)]})
        self.assertIsNone(run([Slot(slot="morphology", text="mụn nước")], kc, RuntimeError("boom"))[0].node_id)

    def test_cache_by_text_and_slot_skips_http(self):
        kc = FakeKnowledge({"effect/phenotype": [exact("1", "Pruritus")]})
        slot = Slot(slot="symptom", text="ngứa", text_en="Pruritus")
        run([slot], kc)
        with patch.object(module, "get_knowledge_client", return_value=kc):
            again = asyncio.run(link_entities(CTX, [Slot(slot="symptom", text="ngứa nhiều", text_en="pruritus")]))
        self.assertEqual(again[0].node_id, "effect/phenotype:1")
        self.assertEqual(len(kc.calls), 1)


if __name__ == "__main__":
    unittest.main()
