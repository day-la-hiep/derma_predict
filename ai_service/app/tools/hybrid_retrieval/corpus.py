from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.tools.hybrid_retrieval.fusion import book_result


@dataclass(frozen=True)
class Corpus:
    name: str  # khớp `corpus` của knowledge `/internal/search/*`
    id_key: str  # khoá payload định danh một kết quả, dùng để khử trùng khi trộn các nhánh
    to_result: Callable[[dict[str, Any]], dict[str, Any]]  # đổi payload thành kết quả trả cho model


DOCUMENT_CORPUS = Corpus(name="document", id_key="chunk_id", to_result=book_result)


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


FINALIZE_REPORT_CORPUS = Corpus(name="finalize_report", id_key="case_id", to_result=case_result)
