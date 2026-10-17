import asyncio
import unittest
from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

from agent.tools.hybrid_retrieval.kg import ExtractedEntity
from agent.tools.hybrid_retrieval.pipeline import expand_query, rank_candidates, run_hybrid, to_candidates


class Fns(TypedDict):
    semantic_fn: Callable[[str, int], Awaitable[list[dict[str, Any]]]]
    bm25_fn: Callable[[str, int], Awaitable[list[dict[str, Any]]]]
    entities_fn: Callable[[str], Awaitable[list[ExtractedEntity]]]
    rerank_fn: Callable[[str, list[str]], Awaitable[list[float] | None]]


def chunk(cid: str) -> dict[str, Any]:
    return {"chunk_id": cid, "document_title": "Sách", "toc_path": ["Chương", cid], "text": f"text {cid}", "context_text": f"ctx {cid}"}


def stubs(sem: list[str], bm25: list[str], scores: dict[str, float] | None, entities: list[ExtractedEntity] | None = None, bm25_queries: list[str] | None = None) -> Fns:
    async def semantic(query: str, limit: int):
        return [chunk(c) for c in sem]

    async def bm25_fn(query: str, limit: int):
        if bm25_queries is not None:
            bm25_queries.append(query)
        return [chunk(c) for c in bm25]

    async def entities_fn(query: str):
        if entities is None:
            raise RuntimeError("llm lỗi")
        return entities

    async def rerank_fn(query: str, passages: list[str]):
        return None if scores is None else [scores[p.split()[1]] for p in passages]

    return Fns(semantic_fn=semantic, bm25_fn=bm25_fn, entities_fn=entities_fn, rerank_fn=rerank_fn)


def run(coro):
    return asyncio.run(coro)


class PipelineTest(unittest.TestCase):
    def test_expand_query_adds_names_once(self) -> None:
        ents = [ExtractedEntity(text="psoriasis", vi="vảy nến", type="disease")]
        self.assertEqual(expand_query("da bong vảy nến", ents), "da bong vảy nến psoriasis")

    def test_rank_rounds_before_sorting_so_close_scores_keep_order(self) -> None:
        cands = to_candidates([chunk("A"), chunk("B"), chunk("C")])
        ranked = run(rank_candidates("q", cands, stubs([], [], {"A": 0.8004, "B": 0.8001, "C": 0.95})["rerank_fn"]))
        self.assertEqual([c["_chunk_id"] for c in ranked or []], ["C", "A", "B"])

    def test_hybrid_reranks_and_exposes_both_orders(self) -> None:
        r = run(run_hybrid("q", **stubs(["A", "B"], ["B", "C"], {"A": 0.1, "B": 0.5, "C": 0.9})))
        self.assertTrue(r.reranked)
        self.assertEqual([c["_chunk_id"] for c in r.candidates], ["B", "A", "C"])  # thứ tự RRF
        self.assertEqual([c["_chunk_id"] for c in r.ranked], ["C", "B", "A"])  # sau rerank

    def test_rerank_unavailable_keeps_rrf_order(self) -> None:
        r = run(run_hybrid("q", **stubs(["A", "B"], ["B", "C"], None)))
        self.assertFalse(r.reranked)
        self.assertEqual(r.ranked, r.candidates)

    def test_entities_failure_falls_back_to_raw_query_with_note(self) -> None:
        seen: list[str] = []
        r = run(run_hybrid("da bong vảy", **stubs(["A"], ["B"], {"A": 0.1, "B": 0.2}, entities=None, bm25_queries=seen)))
        self.assertEqual(seen, ["da bong vảy"])
        self.assertTrue(any("Không mở rộng được query" in n for n in r.notes))

    def test_one_leg_failing_is_noted_and_other_leg_still_used(self) -> None:
        fns = stubs(["A"], ["B"], {"A": 0.3, "B": 0.2}, entities=[])

        async def broken(query: str, limit: int):
            raise RuntimeError("qdrant chết")

        r = run(run_hybrid("q", **{**fns, "semantic_fn": broken}))
        self.assertEqual([c["_chunk_id"] for c in r.ranked], ["B"])
        self.assertTrue(any("semantic" in n and "không dùng được" in n for n in r.notes))

    def test_no_candidates(self) -> None:
        r = run(run_hybrid("q", **stubs([], [], {}, entities=[])))
        self.assertEqual((r.candidates, r.ranked, r.reranked), ([], [], False))


if __name__ == "__main__":
    unittest.main()
