"""Truy cập Qdrant cho chunk sách"""
from typing import Any

from qdrant_client.models import Record

from app.config.settings import settings
from app.infra.qdrant_client import QdrantVectorClient


def _normalize_legacy(payload: dict[str, Any] | None) -> None:
    """Payload collection cũ dùng `book_id`/`book_title`; đưa về tên `document_*` để tool trích dẫn nguồn đúng."""
    if payload:
        payload.setdefault("document_id", payload.get("book_id"))
        payload.setdefault("document_title", payload.get("book_title"))


def document_collections() -> list[str]:
    legacy = settings.QDRANT_LEGACY_BOOK_COLLECTION
    return [settings.QDRANT_DOCUMENT_COLLECTION, *([legacy] if legacy else [])]


def normalize_document(name: str, payload: dict[str, Any] | None) -> None:
    if name == settings.QDRANT_LEGACY_BOOK_COLLECTION:
        _normalize_legacy(payload)


class KnowledgeBaseService:
    def __init__(self, qdrant: QdrantVectorClient) -> None:
        self._qdrant = qdrant

    async def all_document_chunks(self) -> list[Record]:
        """Mọi chunk sách kèm payload, chỉ để thống kê / kiểm tra bằng tay (`agent/test/`); tìm kiếm không đọc cả kho."""
        records: list[Record] = []
        for name in document_collections():
            found = await self._qdrant.scroll_all(name)
            for r in found:
                normalize_document(name, r.payload)
            records += found
        return records
