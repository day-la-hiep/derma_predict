"""Nhánh semantic: knowledge embed câu hỏi rồi tìm trong Qdrant, mặc định là chunk sách của pipeline `document_ingest`."""
from typing import Any

from agent.tools.hybrid_retrieval.corpus import DOCUMENT_CORPUS, Corpus
from app.deps import get_knowledge_client


async def semantic_search(query: str, limit: int, corpus: Corpus = DOCUMENT_CORPUS) -> list[dict[str, Any]]:
    """Payload gần câu hỏi nhất, theo thứ tự giảm dần; rỗng khi nguồn chưa index gì."""
    return await get_knowledge_client().search_semantic(query, limit, corpus=corpus.name)
