import asyncio
import unittest
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

from app.state.v3.facts import Fact
from app.tools.v3 import guideline_search as gs
from app.tools.v3.fuse_scores import PROPOSED_BONUS, fuse_scores
from app.tools.v3.guideline_search import aggregate_by_disease, build_symptom_query, search_by_disease
from app.tools.v3.ids import split_node_id, to_mondo, to_node_ref
from app.tools.v3.kg_rank_diseases import kg_rank_diseases

NOW = datetime(2026, 11, 14, tzinfo=timezone.utc)


def fact(text: str, node: str | None = None, name: str | None = None, assertion: str = "present", source: str = "text", text_en: str = "") -> Fact:
    return Fact.model_validate({"slot": "symptom", "text": text, "text_en": text_en, "node_id": node, "node_name": name, "assertion": assertion, "source": source, "time": NOW})


class IdsTest(unittest.TestCase):
    def test_ids(self):
        self.assertEqual(split_node_id("dermo:DERMO:1"), ("dermo", "DERMO:1"))
        self.assertEqual(to_node_ref("effect/phenotype:989"), {"type": "effect/phenotype", "id": "989"})
        self.assertIsNone(to_node_ref("dermo:DERMO:1"))
        self.assertEqual(to_mondo("disease:5083"), "MONDO:0005083")
        self.assertIsNone(to_mondo("disease:5105_5012"))


class FuseScoresTest(unittest.TestCase):
    def test_normalized_weighted_and_cnn_missing(self):
        hyps = fuse_scores({
            "kg": [{"disease_id": "disease:a", "name": "A", "score": 4.0}, {"disease_id": "disease:b", "name": "B", "score": 2.0}],
            "cnn": [],
            "rag": [{"disease_id": "disease:b", "name": "disease:b", "score": 0.02}],
        })
        self.assertEqual([(h.disease_id, h.score) for h in hyps], [("disease:a", 0.4), ("disease:b", 0.4)])
        self.assertEqual(hyps[1].signals, {"kg": 0.5, "rag": 1.0})
        self.assertEqual(hyps[1].name, "B")  # tên lấy từ nguồn có tên trước

    def test_proposed_kept_beyond_top_k_with_own_score(self):
        kg = [{"disease_id": f"disease:{i}", "name": str(i), "score": 1.0} for i in range(8)]
        hyps = fuse_scores({"kg": kg, "rag": [{"disease_id": "disease:pso", "name": "psoriasis", "score": 1.0}]},
                           proposed=[{"disease_id": "disease:pso", "name": "psoriasis"}], top_k=6)
        self.assertEqual(len(hyps), 7)
        self.assertEqual((hyps[-1].disease_id, hyps[-1].score, hyps[-1].signals), ("disease:pso", 0.2, {"rag": 1.0, "proposed": 1.0}))

    def test_duplicates_merged_and_proposed_appended(self):
        hyps = fuse_scores({"kg": [{"disease_id": "disease:a", "name": "A", "score": 1.0}, {"disease_id": "disease:a", "name": "A", "score": 3.0}]},
                           proposed=[{"disease_id": "disease:z", "name": "Z"}, {"disease_id": "disease:a", "name": "A"}])
        self.assertEqual([(h.disease_id, h.score) for h in hyps], [("disease:a", 0.4), ("disease:z", PROPOSED_BONUS)])


class KgRankTest(unittest.TestCase):
    def test_only_primekg_nodes_and_absent_split(self):
        kc = AsyncMock()
        kc.rank_diseases.return_value = [{"id": "5083", "name": "psoriasis", "score": 3.0, "why": []}]
        facts = [fact("ngứa", "effect/phenotype:989"), fact("sốt", "effect/phenotype:1945", assertion="absent"), fact("mảng", "dermo:D:1"),
                 fact("mẹ bị", "disease:1", assertion="family")]
        with patch("app.tools.v3.kg_rank_diseases.get_knowledge_client", return_value=kc):
            out = asyncio.run(kg_rank_diseases(facts))
        present, absent, _ = kc.rank_diseases.call_args.args
        self.assertEqual((present, absent), ([{"type": "effect/phenotype", "id": "989"}], [{"type": "effect/phenotype", "id": "1945"}]))
        self.assertEqual(out[0]["disease_id"], "disease:5083")


class GuidelineSearchTest(unittest.TestCase):
    def test_symptom_query_uses_standard_names_then_raw_text(self):
        facts = [fact("ngứa", "effect/phenotype:989", "Pruritus"), fact("vảy", text_en="scaling"), fact("đỏ rực"), fact("sốt", assertion="absent", text_en="fever")]
        self.assertEqual(build_symptom_query(facts), "Pruritus scaling đỏ rực")

    def test_aggregate_primary_full_mentioned_weighted(self):
        chunks = [{"chunk_id": "c1", "primary_disease_ids": ["disease:a"], "mentioned_disease_ids": ["disease:b"]},
                  {"chunk_id": "c2", "primary_disease_ids": [], "mentioned_disease_ids": ["disease:b"]}]
        out = {d["disease_id"]: d for d in aggregate_by_disease(chunks)}
        self.assertAlmostEqual(out["disease:a"]["score"], round(1 / 61, 5))
        self.assertAlmostEqual(out["disease:b"]["score"], round(0.3 / 61 + 0.3 / 62, 5))
        self.assertEqual(out["disease:b"]["why"], ["c1", "c2"])

    def test_disease_mode_filters_payload_and_dedups(self):
        calls: list[dict[str, Any]] = []

        class Result:
            ranked = [{"_id": "c1", "text": "t1"}, {"_id": "c2", "text": "t2"}]

        async def fake_run(query: str, **kw: Any) -> Result:
            calls.append({"query": query, **kw})
            return Result()

        kc = AsyncMock()
        with patch.object(gs, "run_hybrid", fake_run), patch.object(gs, "get_knowledge_client", return_value=kc):
            chunks = asyncio.run(search_by_disease("disease:5083", "psoriasis"))
            asyncio.run(calls[0]["semantic_fn"]("q", 5))
        self.assertEqual([c["chunk_id"] for c in chunks], ["c1", "c2"])
        self.assertEqual(chunks[0]["disease_id"], "disease:5083")
        self.assertEqual([c["query"] for c in calls], ["psoriasis diagnosis", "psoriasis differential diagnosis"])
        self.assertEqual(kc.search_semantic.call_args.kwargs["eq"], {"mentioned_disease_ids": "disease:5083"})


if __name__ == "__main__":
    unittest.main()
