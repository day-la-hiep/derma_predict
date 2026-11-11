from typing import Any

from qdrant_client.models import PointStruct

from app.infra.bm25 import SPARSE_NAME, encode_document
from app.infra.qdrant_client import QdrantVectorClient, eq_filter, get_point_id

_PAYLOAD_KEYS = ("chunk_id", "seq", "document_id", "text", "context_text", "toc_path", "toc_node_ids",
                 "figure_ids", "level", "pages_hint", "boundary", "suspect", "page_start", "page_end", "page_printed_start", "page_printed_end",
                 "tokens", "chars")


class DocumentChunkIndex:
    def __init__(self, qdrant: QdrantVectorClient, collection: str) -> None:
        self._qdrant, self.collection = qdrant, collection

    def ensure_collection(self, dim: int) -> None:
        self._qdrant.ensure_collection_sync(self.collection, dim, keyword_index_fields=("document_id",), sparse_names=(SPARSE_NAME,))

    def delete_chunks(self, document_id: str) -> None:
        """Xoá mọi point của tài liệu (no-op khi collection chưa có)."""
        self._qdrant.delete_by_filter_sync(self.collection, eq_filter("document_id", document_id))

    def upsert_chunks(self, document_id: str, chunks: list[dict[str, Any]], vectors: list[list[float]], extra: dict[str, Any]) -> None:
        points = [
            # vector không tên = dense (semantic); "bm25" = sparse để Qdrant chấm điểm từ khoá, cùng văn bản với embedding
            PointStruct(id=get_point_id(c["chunk_id"]), vector={"": v, SPARSE_NAME: encode_document(str(c.get("context_text") or c.get("text") or ""))},
                        payload={**{k: c.get(k) for k in _PAYLOAD_KEYS}, "document_id": document_id, **extra})
            for c, v in zip(chunks, vectors, strict=True)
        ]
        self._qdrant.upsert_points_sync(self.collection, points)
