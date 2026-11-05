"""Nhánh graph của `hybrid_retrieval`: thực thể trong câu hỏi -> cạnh DOC trong Neo4j -> chunk sách mà cạnh trích từ đó"""

from typing import Any

from agent.tools.hybrid_retrieval.corpus import DOCUMENT_CORPUS
from agent.tools.hybrid_retrieval.kg import ExtractedEntity
from app.api.deps import get_document_graph_service, get_retrieval_service
from app.services.retrieval_service import RetrievalCorpus


async def graph_search(
    entities: list[ExtractedEntity],
    limit: int,
    corpus: RetrievalCorpus = DOCUMENT_CORPUS,
) -> list[dict[str, Any]]:
    """Payload chunk theo số cạnh trỏ tới giảm dần; rỗng khi không phải corpus sách, không có thực thể y khoa hoặc chưa có cạnh DOC."""
    if corpus.name != DOCUMENT_CORPUS.name:
        return []
    names = [
        t for e in entities if e.type != "other" for t in (e.text, e.vi) if t
    ]
    chunk_ids = await get_document_graph_service().chunks_for_entities(
        names, limit
    )
    return await get_retrieval_service().fetch(corpus, chunk_ids)
