from agent.common.embeddings import get_embeddings
from agent.tools.hybrid_retrieval.fusion import book_result
from app.infra.bm25 import LANGUAGES
from app.services.knowledge_base_service import document_collections, normalize_document
from app.services.retrieval_service import RetrievalCorpus

DOCUMENT_CORPUS = RetrievalCorpus(
    name="document",
    collections=document_collections,
    id_key="chunk_id",
    sparse_modes=LANGUAGES,
    sparse_mode_field="bm25_mode",
    normalize=normalize_document,
    to_result=book_result,
    embed_query=lambda q: get_embeddings().aembed_query(q),
)
