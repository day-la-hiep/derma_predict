"""Nhánh semantic: embedding local (`agent/embeddings.py`) -> Qdrant, mặc định là chunk sách của pipeline `document_ingest`."""

from typing import Any

from agent.tools.hybrid_retrieval.corpus import DOCUMENT_CORPUS
from app.api.deps import get_retrieval_service
from app.services.retrieval_service import RetrievalFilter, RetrievalCorpus


async def semantic_search(
    query: str,
    limit: int,
    corpus: RetrievalCorpus = DOCUMENT_CORPUS,
    filter: RetrievalFilter | None = None,
) -> list[dict[str, Any]]:
    """Payload gần câu hỏi nhất, theo thứ tự giảm dần; rỗng khi nguồn chưa index gì."""
    vector = await corpus.embed_query(query)
    points = await get_retrieval_service().dense(
        corpus, vector=vector, limit=limit, filter=filter
    )
    return [p.payload for p in points if p.payload]
