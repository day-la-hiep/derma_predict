import unittest
from datetime import datetime, timedelta, timezone

from app.state.v3.facts import Fact, get_fact_weight, merge_facts

NOW = datetime(2026, 11, 14, tzinfo=timezone.utc)


def make(text: str, source: str = "text", node_id: str | None = "HP:1", **kw: object) -> Fact:
    return Fact.model_validate({"slot": "symptom", "text": text, "node_id": node_id, "source": source, "time": NOW, **kw})


class FactTest(unittest.TestCase):
    def test_json_round_trip(self):
        fact = make("ngứa", assertion="absent", provenance=["m1"])
        self.assertEqual(Fact.model_validate(fact.model_dump(mode="json")), fact)

    def test_text_replaces_same_key_image_does_not(self):
        known = [make("ngứa", source="image")]
        self.assertEqual(merge_facts(known, [make("ngứa nhiều")])[0].source, "text")
        known = [make("ngứa")]
        self.assertEqual(merge_facts(known, [make("ngứa?", source="image")])[0].text, "ngứa")

    def test_unlinked_facts_keyed_by_text(self):
        merged = merge_facts([make("Ngứa ", node_id=None)], [make("ngứa", node_id=None), make("đau", node_id=None)])
        self.assertEqual(len(merged), 2)

    def test_weight(self):
        self.assertEqual(get_fact_weight(make("a"), NOW), 1.0)
        self.assertAlmostEqual(get_fact_weight(make("a", source="image"), NOW), 0.6)
        old = make("a", source="history", time=NOW - timedelta(days=365))
        self.assertAlmostEqual(get_fact_weight(old, NOW), 0.4)


if __name__ == "__main__":
    unittest.main()
