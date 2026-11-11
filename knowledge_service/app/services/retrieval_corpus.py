import asyncio

from app.config.settings import settings
from app.infra.embedding_client import EmbeddingClient
from app.services.retrieval_service import RetrievalCorpus


_embedding = EmbeddingClient()


async def embed_query(query: str) -> list[float]:
    return await asyncio.to_thread(_embedding.embed_query, query)


DOCUMENT_CORPUS = RetrievalCorpus(
    name="document",
    collections=lambda: [settings.QDRANT_DOCUMENT_COLLECTION],
    id_key="chunk_id",
    embed_query=embed_query,
)

FINALIZE_REPORT_CORPUS = RetrievalCorpus(
    name="finalize_report",
    collections=lambda: [settings.QDRANT_FINALIZE_REPORT_COLLECTION],
    id_key="case_id",
    embed_query=embed_query,
)

CORPORA = {DOCUMENT_CORPUS.name: DOCUMENT_CORPUS, FINALIZE_REPORT_CORPUS.name: FINALIZE_REPORT_CORPUS}
