"""Truy cập Qdrant cho chunk sách"""
from qdrant_client.models import Record

from app.config.settings import settings
from app.infra.qdrant_client import QdrantVectorClient


def document_collections() -> list[str]:
    return [settings.QDRANT_DOCUMENT_COLLECTION]


class KnowledgeBaseService:
    def __init__(self, qdrant: QdrantVectorClient) -> None:
        self._qdrant = qdrant

    async def all_document_chunks(self) -> list[Record]:
        """Mọi chunk sách kèm payload, chỉ để thống kê / kiểm tra bằng tay (`agent/test/`); tìm kiếm không đọc cả kho."""
        records: list[Record] = []
        for name in document_collections():
            records += await self._qdrant.scroll_all(name)
        return records
