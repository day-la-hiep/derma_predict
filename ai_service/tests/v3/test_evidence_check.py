import asyncio
import unittest
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

from app.state.v3.diagnosis import EvidenceRow, Hypothesis
from app.state.v3.facts import Fact
from app.tools.v3.annotate_guideline import AnnotationItem, validate_annotations
from app.tools.v3.build_evidence_table import build_evidence_table, render_evidence_row
from app.tools.v3.check_stop import MAX_ROUNDS, should_stop
from app.tools.v3.red_flag_rules import check_red_flags, get_urgency
from app.tools.v3.select_discriminator import select_discriminator

NOW = datetime(2026, 11, 14, tzinfo=timezone.utc)
PSO = "disease:5083"
PROFILE = {PSO: {"name": "psoriasis", "positive": [
    {"id": "40189", "name": "Scaling skin", "weight": 1.0}, {"id": "500", "name": "Erythematous plaque", "weight": 0.8},
    {"id": "600", "name": "Nail pitting", "weight": 1.2}, {"id": "700", "name": "Family history", "weight": 0.3},
], "negative": [{"id": "1945", "name": "Fever", "weight": 0.5}]}}


def fact(text: str, node: str | None = None, slot: str = "symptom", assertion: str = "present", text_en: str = "", conflict: bool = False, name: str | None = None) -> Fact:
    return Fact.model_validate({"slot": slot, "text": text, "text_en": text_en, "node_id": node, "node_name": name, "assertion": assertion,
                                "source": "text", "time": NOW, "conflict": conflict})


def hyp(disease_id: str, score: float, name: str = "") -> Hypothesis:
    return Hypothesis(disease_id=disease_id, name=name or disease_id, score=score, signals={"kg": 0.71, "cnn": 0.58})


class EvidenceTableTest(unittest.TestCase):
    def test_psoriasis_example_from_doc(self):
        facts = [fact("vảy", "effect/phenotype:40189", "scale", name="Scaling skin"), fact("mảng đỏ", slot="morphology", text_en="erythematous plaque"),
                 fact("khuỷu tay", slot="location"), fact("ngứa dữ dội", "effect/phenotype:989", name="Severe pruritus")]
        row = build_evidence_table(facts, PROFILE, [hyp(PSO, 0.9, "Psoriasis")], [], NOW)[0]
        self.assertEqual(row.matched, ["effect/phenotype:40189", "effect/phenotype:500"])  # mảng đỏ khớp chữ
        self.assertEqual(row.missing[0], "effect/phenotype:600")
        self.assertEqual((row.contradicted, row.unexplained), ([], ["Severe pruritus"]))
        self.assertAlmostEqual(row.score, 1.0 + 0.8 * 0.5)
        text = render_evidence_row(row, hyp(PSO, 0.9, "Psoriasis"))
        self.assertIn("[Psoriasis | disease:5083 | KG 0.71 | CNN 0.58]", text)
        self.assertIn("Khớp: Scaling skin, Erythematous plaque", text)

    def test_contradictions_and_asked(self):
        facts = [fact("vảy", "effect/phenotype:40189", assertion="absent"), fact("sốt", "effect/phenotype:1945")]
        row = build_evidence_table(facts, PROFILE, [hyp(PSO, 0.5)], ["effect/phenotype:600"], NOW)[0]
        self.assertEqual(set(row.contradicted), {"effect/phenotype:40189", "effect/phenotype:1945"})
        self.assertNotIn("effect/phenotype:600", row.missing)
        self.assertAlmostEqual(row.score, -1.5)


class AnnotateTest(unittest.TestCase):
    def test_validation_drops_bad_items(self):
        facts = [fact("vảy", name="Scaling skin")]
        chunks = [{"chunk_id": "c1", "text": "Psoriasis presents with   silvery scaling plaques."}]
        items = [
            AnnotationItem(fact_index=1, stance="support", chunk_id="c1", quote="silvery scaling plaques"),
            AnnotationItem(fact_index=1, stance="support", chunk_id="c9", quote="silvery"),
            AnnotationItem(fact_index=2, stance="support", chunk_id="c1", quote="silvery"),
            AnnotationItem(fact_index=1, stance="refute", chunk_id="c1", quote="never scaly"),
            AnnotationItem(fact_index=1, stance="irrelevant", chunk_id="c1", quote="silvery"),
        ]
        notes = validate_annotations(items, facts, chunks)
        self.assertEqual([(n.fact, n.chunk_id, n.quote) for n in notes], [("Scaling skin", "c1", "silvery scaling plaques")])


class RedFlagTest(unittest.TestCase):
    def test_urgent_disease_in_top3(self):
        flags = check_red_flags([], [hyp("disease:1", 0.9), hyp("disease:18229", 0.5)], [])
        self.assertEqual((flags[0]["urgency"], get_urgency(flags)), ("urgent", "urgent"))

    def test_combo_needs_all_parts(self):
        facts = [fact("sốt", "effect/phenotype:1945"), fact("loét miệng", slot="morphology")]
        self.assertEqual(check_red_flags(facts, [], []), [])
        flags = check_red_flags(facts, [], [{"drug_id": "drug:DB1", "name": "allopurinol"}])
        self.assertIn("SJS/TEN", flags[0]["name"])
        self.assertEqual(get_urgency([]), "routine")

    def test_absent_symptom_does_not_trigger(self):
        facts = [fact("sốt", "effect/phenotype:1945", assertion="absent"), fact("lan nhanh", slot="distribution")]
        self.assertEqual(check_red_flags(facts, [], []), [])


class StopTest(unittest.TestCase):
    def test_conditions(self):
        two = [hyp("a", 0.8), hyp("b", 0.5)]
        self.assertFalse(should_stop(two, [EvidenceRow(disease_id="a", matched=["x", "y"])], 0, True)[0])  # khớp ít: hỏi tiếp
        self.assertTrue(should_stop(two, [EvidenceRow(disease_id="a", matched=["x", "y", "z"])], 0, True)[0])
        close = [hyp("a", 0.6), hyp("b", 0.5)]
        self.assertEqual(should_stop(close, [], 0, True), (False, "chưa đủ chắc, cần hỏi thêm"))
        self.assertTrue(should_stop(close, [], MAX_ROUNDS, True)[0])
        self.assertTrue(should_stop(close, [], 0, False)[0])
        one = [hyp("a", 0.4)]
        self.assertTrue(should_stop(one, [EvidenceRow(disease_id="a", matched=["x", "y"])], 0, True)[0])


class DiscriminatorTest(unittest.TestCase):
    def run_select(self, facts: list[Fact], ambiguous: list[dict[str, Any]], asked: list[str], questions: list[dict[str, Any]] | None = None) -> Any:
        kc = AsyncMock()
        kc.get_discriminating_questions_by_ids.return_value = {"questions": questions or []}
        rows = [EvidenceRow(disease_id="disease:a", missing=["effect/phenotype:600"], names={"effect/phenotype:600": "Nail pitting"})]
        with patch("app.tools.v3.select_discriminator.get_knowledge_client", return_value=kc):
            return asyncio.run(select_discriminator(facts, ambiguous, [hyp("disease:a", 0.6), hyp("disease:b", 0.5)], rows, asked)), kc

    def test_priority_conflict_then_ambiguous_then_graph_then_missing(self):
        conflict = fact("đỏ", "effect/phenotype:1", slot="color", conflict=True)
        amb = [{"slot": "morphology", "text": "bọng", "node_id": "effect/phenotype:3", "node_name": "Bulla"}]
        q = [{"primekg_id": "1945", "phenotype": "Fever", "present_in": ["a"], "absent_in": ["b"]}]
        self.assertEqual(self.run_select([conflict], amb, [], q)[0]["kind"], "conflict")
        self.assertEqual(self.run_select([conflict], amb, ["conflict:color:effect/phenotype:1"], q)[0]["kind"], "ambiguous")
        out, kc = self.run_select([fact("ngứa", "effect/phenotype:989")], [], [], q)
        self.assertEqual((out["kind"], out["node_id"], out["present_in"]), ("discriminate", "effect/phenotype:1945", ["disease:a"]))
        self.assertEqual(kc.get_discriminating_questions_by_ids.call_args.args, (["a", "b"], ["989"]))
        self.assertEqual(self.run_select([], [], ["effect/phenotype:1945"], q)[0]["kind"], "missing")
        self.assertIsNone(self.run_select([], [], ["effect/phenotype:600"])[0])

    def test_not_askable_phenotypes_skipped(self):
        q = [{"primekg_id": "7", "phenotype": "Autosomal recessive inheritance", "present_in": ["a"], "absent_in": ["b"]},
             {"primekg_id": "1945", "phenotype": "Fever", "present_in": ["a"], "absent_in": ["b"]}]
        self.assertEqual(self.run_select([], [], [], q)[0]["node_id"], "effect/phenotype:1945")


if __name__ == "__main__":
    unittest.main()
