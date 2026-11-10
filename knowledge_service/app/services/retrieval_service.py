import asyncio
import logging
import uuid
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
    # phải là model đã embed lúc index nguồn này, nếu không dense search so vector khác không gian; service không dùng
    embed_query: Callable[[str], Awaitable[list[float]]]
    sparse_modes: tuple[str, ...] = ("mixed",)
    # payload ghi lại cách mã hoá BM25 của từng point; query phải mã hoá cùng cách nên lọc theo field này
    sparse_mode_field: str | None = None
    base_filter: RetrievalFilter = RetrievalFilter()


def _qdrant_filter(*filters: RetrievalFilter | None) -> Filter | None:
    merged = RetrievalFilter()
    for f in filters:
        merged = merged.merge(f)
    return build_filter(merged.eq, merged.any_of)


class RetrievalService:
    def __init__(self, qdrant: QdrantVectorClient) -> None:
        self._qdrant = qdrant

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
                points += group
        return sorted(points, key=lambda p: p.score, reverse=True)[:limit]

    async def fetch(self, corpus: RetrievalCorpus, ids: list[str]) -> list[dict[str, Any]]:
        """Payload theo `corpus.id_key` (point id = uuid5 của id, như lúc index), giữ thứ tự `ids`; id không thấy thì bỏ."""
        point_ids = {i: str(uuid.uuid5(uuid.NAMESPACE_URL, i)) for i in ids}
        found: dict[str, dict[str, Any]] = {}
        for name in corpus.collections():
            for payload in await self._qdrant.retrieve_payloads(name, list(point_ids.values())):
                found[str(payload.get(corpus.id_key))] = payload
        missing = [i for i in ids if i not in found]
        if missing:
            logger.warning("[retrieval:%s] %d/%d chunk của graph không có trong Qdrant (chunk lại / index lại sau graph?): %s",
                           corpus.name, len(missing), len(ids), missing[:5])
        return [found[i] for i in ids if i in found]
