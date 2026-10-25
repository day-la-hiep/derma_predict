import asyncio
import unittest
from types import SimpleNamespace
from typing import Any

from qdrant_client.models import Filter, MatchAny, MatchValue, SparseVector

from app.infra.qdrant_client import build_filter
from app.services.retrieval_service import RetrievalFilter, RetrievalService, RetrievalCorpus


def point(pid: str, score: float, **payload: Any) -> Any:
    return SimpleNamespace(id=pid, score=score, payload={"pid": pid, **payload})


class FakeQdrant:
    def __init__(self, dims: dict[str, int], sparse: set[str]) -> None:
        self.dims, self.sparse = dims, sparse
        self.calls: list[tuple[str, Filter | None]] = []

    async def dense_size(self, name: str) -> int | None:
        return self.dims.get(name)

    async def has_sparse_vector(self, name: str, vector_name: str) -> bool:
        return name in self.sparse

    async def search(self, name: str, vector: list[float], *, limit: int, query_filter: Filter | None = None) -> list[Any]:
        self.calls.append((name, query_filter))
        return [point(f"{name}-d", 0.5)]

    async def search_sparse(self, name: str, vector: SparseVector, *, using: str, limit: int, query_filter: Filter | None = None) -> list[Any]:
        self.calls.append((name, query_filter))
        return [point(f"{name}-s", 0.7)]


async def _embed(q: str) -> list[float]:
    return [0.0]


def corpus(**kw: Any) -> RetrievalCorpus:
    return RetrievalCorpus(name="t", collections=lambda: ["a", "b"], id_key="pid", to_result=lambda p: p, embed_query=_embed, **kw)


def run(coro: Any) -> Any:
    return asyncio.run(coro)


class BuildFilterTest(unittest.TestCase):
    def test_empty_is_none(self) -> None:
        self.assertIsNone(build_filter({}, {}))

    def test_eq_and_any_of_are_anded(self) -> None:
        f = build_filter({"document_id": "d1"}, {"diagnosis": ["x", "y"]})
        assert f is not None and isinstance(f.must, list)
        self.assertEqual(f.must[0].match, MatchValue(value="d1"))  # type: ignore[union-attr]
        self.assertEqual(f.must[1].match, MatchAny(any=["x", "y"]))  # type: ignore[union-attr]

    def test_merge_caller_overrides_and_keeps_other_keys(self) -> None:
        merged = RetrievalFilter(eq={"a": 1, "b": 2}).merge(RetrievalFilter(eq={"b": 3}, any_of={"c": [1]}))
        self.assertEqual((merged.eq, merged.any_of), ({"a": 1, "b": 3}, {"c": [1]}))


class RetrievalServiceTest(unittest.TestCase):
    def test_dense_skips_collections_with_other_dimension(self) -> None:
        q = FakeQdrant({"a": 3, "b": 4}, set())
        points = run(RetrievalService(q).dense(corpus(), vector=[0.0] * 3, limit=5))  # type: ignore[arg-type]
        self.assertEqual([p.id for p in points], ["a-d"])

    def test_sparse_skips_collections_without_sparse_vector(self) -> None:
        q = FakeQdrant({}, {"b"})
        points = run(RetrievalService(q).sparse(corpus(), query="vảy nến", limit=5))  # type: ignore[arg-type]
        self.assertEqual([p.id for p in points], ["b-s"])

    def test_sparse_runs_each_mode_with_its_own_filter_anded_with_base_and_caller(self) -> None:
        q = FakeQdrant({}, {"a"})
        src = RetrievalCorpus(
            name="t", collections=lambda: ["a"], id_key="pid", to_result=lambda p: p, embed_query=_embed, sparse_modes=("vi", "en"), sparse_mode_field="bm25_mode",
            base_filter=RetrievalFilter(eq={"ref": True}),
        )
        run(RetrievalService(q).sparse(src, query="x", limit=5, filter=RetrievalFilter(eq={"document_id": "d1"})))  # type: ignore[arg-type]
        self.assertEqual(len(q.calls), 2)
        for (_, f), mode in zip(q.calls, ("vi", "en"), strict=True):
            assert f is not None and isinstance(f.must, list)
            self.assertEqual({c.key: c.match.value for c in f.must}, {"ref": True, "document_id": "d1", "bm25_mode": mode})  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
