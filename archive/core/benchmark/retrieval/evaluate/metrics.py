import math


def hit_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    return float(any(c in relevant for c in ranked[:k]))


def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    return len(relevant.intersection(ranked[:k])) / len(relevant) if relevant else 0.0


def mrr_at_k(ranked: list[str], relevant: set[str], k: int = 10) -> float:
    for rank, c in enumerate(ranked[:k], start=1):
        if c in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(ranked: list[str], grades: dict[str, int], k: int = 10) -> float:
    def dcg(gs: list[int]) -> float:
        return sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(gs))

    ideal = dcg(sorted(grades.values(), reverse=True)[:k])
    return dcg([grades.get(c, 0) for c in ranked[:k]]) / ideal if ideal > 0 else 0.0
