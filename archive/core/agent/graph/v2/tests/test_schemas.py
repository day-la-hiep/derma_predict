import unittest

from agent.graph.v2.schemas import PlanInput, ReflectInput


class QueriesCoerceTest(unittest.TestCase):
    def test_plan_queries_as_objects(self) -> None:
        plan = PlanInput.model_validate({"hypotheses": [], "queries": [{"disease": "Vảy nến"}, {"x": 1}, "Nấm da đầu"]})
        self.assertEqual(plan.queries, ["Vảy nến", "Nấm da đầu"])

    def test_reflect_queries_as_objects(self) -> None:
        r = ReflectInput.model_validate({"answered": "a", "hypotheses": [], "next": "retrieve", "next_reason": "r", "queries": [{"disease": "Tinea"}]})
        self.assertEqual(r.queries, ["Tinea"])


if __name__ == "__main__":
    unittest.main()
