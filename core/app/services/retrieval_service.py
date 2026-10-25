import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from qdrant_client.models import Filter, ScoredPoint

from app.infra.bm25 import SPARSE_NAME, encode_query
from app.infra.qdrant_client import QdrantVectorClient, build_filter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrievalFilter:
    eq: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    any_of: dict[str, list[Any]] = field(default_factory=lambda: dict[str, list[Any]]())

    def merge(self, other: "RetrievalFilter | None") -> "RetrievalFilter":
        if other is None:
            return self
        return RetrievalFilter({**self.eq, **other.eq}, {**self.any_of, **other.any_of})


@dataclass(frozen=True)
class RetrievalCorpus:
    name: str
    collections: Callable[[], list[str]]
    id_key: str  # khoá payload định danh một kết quả, dùng để khử trùng khi trộn các nhánh
    to_result: Callable[[dict[str, Any]], dict[str, Any]]  # service không dùng; pipeline của agent đổi payload thành kết quả trả cho model
    # phải là model đã embed lúc index nguồn này, nếu không dense search so vector khác không gian; service không dùng
    embed_query: Callable[[str], Awaitable[list[float]]]
    sparse_modes: tuple[str, ...] = ("mixed",)
    # payload ghi lại cách mã hoá BM25 của từng point; query phải mã hoá cùng cách nên lọc theo field này
    sparse_mode_field: str | None = None
    normalize: Callable[[str, dict[str, Any] | None], None] | None = None
    base_filter: RetrievalFilter = RetrievalFilter()


def _qdrant_filter(*filters: RetrievalFilter | None) -> Filter | None:
    merged = RetrievalFilter()
    for f in filters:
        merged = merged.merge(f)
    return build_filter(merged.eq, merged.any_of)


class RetrievalService:
    def __init__(self, qdrant: QdrantVectorClient) -> None:
        self._qdrant = qdrant

    @staticmethod
    def _normalize(corpus: RetrievalCorpus, name: str, points: list[ScoredPoint]) -> None:
        if corpus.normalize:
            for p in points:
                corpus.normalize(name, p.payload)

    async def dense(
        self, corpus: RetrievalCorpus, *, vector: list[float], limit: int, filter: RetrievalFilter | None = None
    ) -> list[ScoredPoint]:
        query_filter = _qdrant_filter(corpus.base_filter, filter)
        points: list[ScoredPoint] = []
        for name in corpus.collections():
            # collection cũ (vd 384 chiều) không so được với embedding hiện tại; query vào sẽ 400 làm hỏng cả nhánh semantic
            size = await self._qdrant.dense_size(name)
            if size != len(vector):
                logger.warning("[retrieval:%s] bỏ qua collection %s: vector %s chiều, query %d chiều", corpus.name, name, size, len(vector))
                continue
            found = await self._qdrant.search(name, vector, limit=limit, query_filter=query_filter)
            self._normalize(corpus, name, found)
            points += found
        return sorted(points, key=lambda p: p.score, reverse=True)[:limit]

    async def sparse(
        self, corpus: RetrievalCorpus, *, query: str, limit: int, filter: RetrievalFilter | None = None
    ) -> list[ScoredPoint]:
        points: list[ScoredPoint] = []
        for name in corpus.collections():
            if not await self._qdrant.has_sparse_vector(name, SPARSE_NAME):
                logger.warning("[retrieval:%s] bỏ qua nhánh BM25 của collection %s: không có sparse vector %s", corpus.name, name, SPARSE_NAME)
                continue
            variants = [
                _qdrant_filter(
                    corpus.base_filter,
                    filter,
                    RetrievalFilter(eq={corpus.sparse_mode_field: mode}) if corpus.sparse_mode_field else None,
                )
                for mode in corpus.sparse_modes
            ]
            found = await asyncio.gather(
                *(
                    self._qdrant.search_sparse(name, encode_query(query, mode), using=SPARSE_NAME, limit=limit, query_filter=f)
                    for mode, f in zip(corpus.sparse_modes, variants, strict=True)
                )
            )
            for group in found:
                self._normalize(corpus, name, group)
                points += group
        return sorted(points, key=lambda p: p.score, reverse=True)[:limit]
