import math
import unittest

from benchmark.common.stats import bootstrap_ci, paired_diff_ci
from benchmark.retrieval.evaluate.metrics import hit_at_k, mrr_at_k, ndcg_at_k, recall_at_k


class MetricsTest(unittest.TestCase):
    ranked = ["a", "b", "c", "d"]

    def test_hit_recall_mrr(self) -> None:
        rel = {"c", "z"}
        self.assertEqual(hit_at_k(self.ranked, rel, 2), 0.0)
        self.assertEqual(hit_at_k(self.ranked, rel, 3), 1.0)
        self.assertEqual(recall_at_k(self.ranked, rel, 4), 0.5)
        self.assertAlmostEqual(mrr_at_k(self.ranked, rel), 1 / 3)
        self.assertEqual(mrr_at_k(self.ranked, {"z"}), 0.0)

    def test_ndcg(self) -> None:
        # xếp đúng thứ tự lý tưởng -> 1
        self.assertAlmostEqual(ndcg_at_k(["x", "y"], {"x": 2, "y": 1}), 1.0)
        # đảo thứ tự: (1/log2(2) + 3/log2(3)) so với (3 + 1/log2(3))
        got = ndcg_at_k(["y", "x"], {"x": 2, "y": 1})
        want = (1 + 3 / math.log2(3)) / (3 + 1 / math.log2(3))
        self.assertAlmostEqual(got, want)
        self.assertEqual(ndcg_at_k(["x"], {}), 0.0)


class StatsTest(unittest.TestCase):
    def test_bootstrap_constant(self) -> None:
        self.assertEqual(bootstrap_ci([1.0] * 10, n_boot=200), (1.0, 1.0, 1.0))

    def test_paired_diff(self) -> None:
        m, lo, hi = paired_diff_ci([1, 1, 1, 0], [0, 0, 0, 0], n_boot=500)
        self.assertAlmostEqual(m, 0.75)
        self.assertLessEqual(lo, m)
        self.assertGreaterEqual(hi, m)
        with self.assertRaises(ValueError):
            paired_diff_ci([1], [1, 0])


if __name__ == "__main__":
    unittest.main()
