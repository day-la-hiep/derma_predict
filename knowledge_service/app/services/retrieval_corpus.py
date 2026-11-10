import asyncio

from app.config.settings import settings
from app.infra.bm25 import LANGUAGES
from app.infra.embeddings import get_embeddings
from app.services.retrieval_service import RetrievalCorpus


async def embed_query(query: str) -> list[float]:
    return await asyncio.to_thread(get_embeddings().embed_query, query)


DOCUMENT_CORPUS = RetrievalCorpus(
    name="document",
    collections=lambda: [settings.QDRANT_DOCUMENT_COLLECTION],
    id_key="chunk_id",
    sparse_modes=LANGUAGES,
    sparse_mode_field="bm25_mode",
    embed_query=embed_query,
)

FINALIZE_REPORT_CORPUS = RetrievalCorpus(
    name="finalize_report",
    collections=lambda: [settings.QDRANT_FINALIZE_REPORT_COLLECTION],
    id_key="case_id",
    # ca bệnh luôn mã hoá BM25 ở chế độ "mixed" lúc index và payload không có `bm25_mode`, nên không lọc theo field đó
    sparse_modes=("mixed",),
    embed_query=embed_query,
)

CORPORA = {DOCUMENT_CORPUS.name: DOCUMENT_CORPUS, FINALIZE_REPORT_CORPUS.name: FINALIZE_REPORT_CORPUS}
