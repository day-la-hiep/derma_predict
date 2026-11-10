"""Nhánh từ khoá của `hybrid_retrieval`"""
from typing import Any

from agent.tools.hybrid_retrieval.corpus import DOCUMENT_CORPUS, Corpus
from app.deps import get_knowledge_client


async def bm25_search(query: str, limit: int, corpus: Corpus = DOCUMENT_CORPUS) -> list[dict[str, Any]]:
    """Payload khớp từ khoá nhất, theo thứ tự giảm dần; rỗng khi nguồn chưa index gì (hoặc không từ nào trùng)."""
    return await get_knowledge_client().search_bm25(query, limit, corpus=corpus.name)
