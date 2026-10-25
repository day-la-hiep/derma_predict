from typing import Any

from agent.common.embeddings import get_embeddings
from agent.tools.hybrid_retrieval.fusion import book_result
from app.config.settings import settings
from app.infra.bm25 import LANGUAGES
from app.services.knowledge_base_service import document_collections
from app.services.retrieval_service import RetrievalCorpus

DOCUMENT_CORPUS = RetrievalCorpus(
    name="document",
    collections=document_collections,
    id_key="chunk_id",
    sparse_modes=LANGUAGES,
    sparse_mode_field="bm25_mode",
    to_result=book_result,
    embed_query=lambda q: get_embeddings().aembed_query(q),
)


def case_result(payload: dict[str, Any]) -> dict[str, Any]:
    # `images` giữ thô: presigned URL cần file store nên tool gắn sau
    return {
        "case_id": payload.get("case_id"),
        "diagnosis": payload.get("diagnosis"),
        "patient_info": {
            "gender": payload.get("gender"),
            "age": payload.get("age"),
            "allergies": payload.get("allergies"),
            "medical_history": payload.get("medical_history"),
        },
        "symptoms_and_facts": payload.get("clinical_facts", []),
        "doctor_assessment": payload.get("reasoning"),
        "urgency": payload.get("urgency"),
        "treatment_instructions": payload.get("instructions"),
        "doctor_notes": payload.get("notes"),
        "case_summary": payload.get("text", ""),
        "images": payload.get("images") or [],
    }


FINALIZE_REPORT_CORPUS = RetrievalCorpus(
    name="finalize_report",
    collections=lambda: [settings.QDRANT_FINALIZE_REPORT_COLLECTION],
    id_key="case_id",
    # ca bệnh luôn mã hoá BM25 ở chế độ "mixed" lúc index và payload không có `bm25_mode`, nên không lọc theo field đó
    sparse_modes=("mixed",),
    to_result=case_result,
    embed_query=lambda q: get_embeddings().aembed_query(q),
)
