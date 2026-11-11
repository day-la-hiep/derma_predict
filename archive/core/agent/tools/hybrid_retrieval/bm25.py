"""Nhánh từ khoá của `hybrid_retrieval`"""
from typing import Any

from agent.tools.hybrid_retrieval.corpus import DOCUMENT_CORPUS
from app.api.deps import get_retrieval_service
from app.services.retrieval_service import RetrievalFilter, RetrievalCorpus


async def bm25_search(query: str, limit: int, corpus: RetrievalCorpus = DOCUMENT_CORPUS, filter: RetrievalFilter | None = None) -> list[dict[str, Any]]:
    """Payload khớp từ khoá nhất, theo thứ tự giảm dần; rỗng khi nguồn chưa index gì (hoặc không từ nào trùng)."""
    points = await get_retrieval_service().sparse(corpus, query=query, limit=limit, filter=filter)
    return [p.payload for p in points if p.payload]
