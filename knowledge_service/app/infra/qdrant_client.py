"""Qdrant dùng chung"""
import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient, QdrantClient
from qdrant_client.models import (
    CollectionParams,
    Condition,
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchAny,
    MatchValue,
    Modifier,
    PayloadSchemaType,
    PointStruct,
    ScoredPoint,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from app.config.settings import settings


def get_point_id(key: str) -> str:
    """Point id suy ra từ khoá nghiệp vụ; lúc index và lúc truy xuất phải cùng công thức này."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def eq_filter(key: str, value: Any) -> Filter:
    """Bộ lọc payload `key == value`."""
    return Filter(must=[FieldCondition(key=key, match=MatchValue(value=value))])


def build_filter(eq: dict[str, Any], any_of: dict[str, list[Any]]) -> Filter | None:
    """AND của các điều kiện `key == value` và `key ∈ values`; `None` khi không có điều kiện nào."""
    must: list[Condition] = [FieldCondition(key=k, match=MatchValue(value=v)) for k, v in eq.items()]
    must += [FieldCondition(key=k, match=MatchAny(any=vs)) for k, vs in any_of.items()]
    return Filter(must=must) if must else None


class QdrantVectorClient:
    def __init__(self, url: str, api_key: str | None = None, *, sync_client: QdrantClient | None = None) -> None:
        """`sync_client` cho phép thay client đồng bộ (test dùng `QdrantClient(":memory:")`)."""
        self.client = AsyncQdrantClient(url=url, api_key=api_key or None)  # API tìm kiếm (async)
        self.sync_client = sync_client or QdrantClient(url=url, api_key=api_key or None)  # pipeline ở thread nền (đồng bộ)

    @classmethod
    def from_settings(cls) -> "QdrantVectorClient":
        return cls(settings.QDRANT_URL, settings.QDRANT_API_KEY or None)

    async def close(self) -> None:
        await self.client.close()
        self.sync_client.close()

    # ---------------------------------------------------------------- async (tìm kiếm)
    async def _params(self, name: str) -> CollectionParams | None:
        """Cấu hình vector của collection; None khi collection chưa có."""
        if not await self.client.collection_exists(name):
            return None
        return (await self.client.get_collection(name)).config.params

    async def search(self, name: str, vector: list[float], *, limit: int, query_filter: Filter | None = None) -> list[ScoredPoint]:
        return (await self.client.query_points(name, query=vector, query_filter=query_filter, limit=limit)).points

    async def search_sparse(self, name: str, vector: SparseVector, *, using: str, limit: int,
                            query_filter: Filter | None = None) -> list[ScoredPoint]:
        """Tìm theo sparse vector đã đặt tên (BM25); chỉ trả point có điểm > 0, tức có ít nhất một từ trùng."""
        if not vector.indices:
            return []
        return (await self.client.query_points(name, query=vector, using=using, query_filter=query_filter, limit=limit)).points

    async def retrieve_payloads(self, name: str, point_ids: list[str]) -> list[dict[str, Any]]:
        """Payload của các point theo id (không cần vector); id không có thì bị bỏ, collection chưa có -> rỗng."""
        if not point_ids or not await self.client.collection_exists(name):
            return []
        records = await self.client.retrieve(name, ids=point_ids, with_payload=True, with_vectors=False)
        by_id = {str(r.id): r.payload for r in records if r.payload}
        return [by_id[i] for i in point_ids if i in by_id]

    async def has_sparse_vector(self, name: str, vector_name: str) -> bool:
        params = await self._params(name)
        return params is not None and vector_name in (params.sparse_vectors or {})

    async def dense_size(self, name: str) -> int | None:
        """Số chiều vector dense; None khi collection chưa có hoặc dùng nhiều vector đặt tên."""
        params = await self._params(name)
        return getattr(params.vectors, "size", None) if params is not None else None

    # ---------------------------------------------------------------- đồng bộ (nạp dữ liệu)
    def ensure_collection_sync(self, name: str, dim: int, *, keyword_index_fields: tuple[str, ...] = (),
                               sparse_names: tuple[str, ...] = ()) -> None:
        """Tạo collection nếu chưa có; có rồi thì kiểm tra khớp số chiều và sparse vector."""
        client = self.sync_client
        if not client.collection_exists(name):
            client.create_collection(
                name,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                sparse_vectors_config={n: SparseVectorParams(modifier=Modifier.IDF) for n in sparse_names} or None,
            )
        info = client.get_collection(name)
        params = info.config.params
        size = getattr(params.vectors, "size", None)
        if size != dim:
            raise RuntimeError(f"Collection {name} có vector {size} chiều, khác embedding hiện tại ({dim} chiều).")
        missing = [n for n in sparse_names if n not in (params.sparse_vectors or {})]
        if missing:
            raise RuntimeError(
                f"Collection {name} thiếu sparse vector {', '.join(missing)} và Qdrant không thêm được vào collection đã tạo — "
                "đặt QDRANT_DOCUMENT_COLLECTION sang tên mới rồi chạy lại bước Lưu vào kho tri thức."
            )
        for field in keyword_index_fields:
            if field not in info.payload_schema:
                client.create_payload_index(name, field_name=field, field_schema=PayloadSchemaType.KEYWORD)

    def delete_by_filter_sync(self, name: str, query_filter: Filter) -> None:
        if self.sync_client.collection_exists(name):
            self.sync_client.delete(name, points_selector=FilterSelector(filter=query_filter), wait=True)

    def upsert_points_sync(self, name: str, points: list[PointStruct]) -> None:
        self.sync_client.upsert(name, points=points, wait=True)
