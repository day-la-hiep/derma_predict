"""Nhánh graph của `hybrid_retrieval`: thực thể trong câu hỏi -> cạnh DOC trong Neo4j -> chunk sách mà cạnh trích từ đó (do knowledge làm)"""
from typing import Any

from agent.tools.hybrid_retrieval.corpus import DOCUMENT_CORPUS, Corpus
from agent.tools.hybrid_retrieval.kg import ExtractedEntity
from app.deps import get_knowledge_client


async def graph_search(entities: list[ExtractedEntity], limit: int, corpus: Corpus = DOCUMENT_CORPUS) -> list[dict[str, Any]]:
    """Payload chunk theo số cạnh trỏ tới giảm dần; rỗng khi không phải corpus sách, không có thực thể y khoa hoặc chưa có cạnh DOC."""
    names = [t for e in entities if e.type != "other" for t in (e.text, e.vi) if t]
    if corpus.name != DOCUMENT_CORPUS.name or not names:
        return []
    return await get_knowledge_client().search_by_graph(names, limit)
