import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from qdrant_client.models import PointStruct

from app.config.settings import settings
from app.dto.request.case import CaseInput
from app.infra.bm25 import SPARSE_NAME, encode_document
from app.infra.embedding_client import EmbeddingClient
from app.infra.qdrant_client import QdrantVectorClient, eq_filter


def get_point_id(case_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"case:{case_id}"))


def build_case_text(case: CaseInput, age: int | None) -> str:
    """Văn bản để embedding; đã bỏ họ tên và số điện thoại để ẩn danh bệnh nhân."""
    patient, assessment = case.snapshot.patient_profile, case.snapshot.assessment
    traits = [
        f"Giới tính: {patient.gender}" if patient.gender else "",
        f"Tuổi: {age}" if age is not None else "",
        f"Tiền sử bệnh: {patient.medical_history}" if patient.medical_history else "",
        f"Tiền sử dị ứng: {patient.allergies}" if patient.allergies else "",
    ]
    image_labels = list(dict.fromkeys(
        v for img in case.images for v in (img.confirmed_label, img.description, img.body_site) if v
    ))
    confirmed = sorted({img.confirmed_label for img in case.images if img.confirmed_label})
    lines = [
        f"Chẩn đoán ca bệnh: {case.diagnosis}",
        f"Đặc điểm bệnh nhân: {', '.join(t for t in traits if t)}" if any(traits) else "",
        "Dữ kiện lâm sàng & Triệu chứng ghi nhận:" if case.snapshot.clinical_facts else "",
        *(f"- [{f.fact_type}] {f.label}: {f.detail}" for f in case.snapshot.clinical_facts),
        f"Đánh giá & Cơ sở chẩn đoán của bác sĩ: {assessment.reasoning}" if assessment.reasoning else "",
        f"Mức độ khẩn cấp: {assessment.urgency}" if assessment.urgency else "",
        f"Dặn dò & Hướng xử trí: {'; '.join(assessment.instructions)}" if assessment.instructions else "",
        f"Ghi chú bổ sung: {case.notes}" if case.notes else "",
        f"Ảnh bệnh đã lưu: {'; '.join(image_labels)}" if image_labels else "",
        f"Nhãn ảnh xác nhận: {', '.join(confirmed)}" if confirmed else "",
    ]
    return "\n".join(line for line in lines if line)


def build_case_payload(case: CaseInput) -> dict[str, Any]:
    patient, assessment = case.snapshot.patient_profile, case.snapshot.assessment
    age = max(datetime.now(UTC).year - patient.dob.year, 0) if patient.dob else None
    return {
        "case_id": case.report_id,
        "diagnosis": case.diagnosis,
        "notes": case.notes,
        "gender": patient.gender,
        "age": age,
        "allergies": patient.allergies,
        "medical_history": patient.medical_history,
        "clinical_facts": [f.model_dump() for f in case.snapshot.clinical_facts],
        "reasoning": assessment.reasoning,
        "urgency": assessment.urgency,
        "instructions": assessment.instructions,
        "is_reference_case": case.is_reference_case,
        "text": build_case_text(case, age),
        "created_at": case.created_at.isoformat(),
        "images": [img.model_dump(exclude={"file_id"}) for img in case.images],
    }


class CaseIndexService:
    def __init__(self, qdrant: QdrantVectorClient, embedding: EmbeddingClient) -> None:
        self._qdrant = qdrant
        self._embedding = embedding
        self._collection = settings.QDRANT_FINALIZE_REPORT_COLLECTION

    def index_case(self, case: CaseInput) -> None:
        self._qdrant.ensure_collection_sync(
            self._collection,
            settings.EMBEDDING_DIM,
            keyword_index_fields=("case_id", "is_reference_case", "diagnosis"),
            sparse_names=(SPARSE_NAME,),
        )
        payload = build_case_payload(case)
        vectors, _, _ = self._embedding.embed([payload["text"]])
        point = PointStruct(
            id=get_point_id(case.report_id),
            vector={"": vectors[0], SPARSE_NAME: encode_document(payload["text"], "mixed")},
            payload=payload,
        )
        self._qdrant.upsert_points_sync(self._collection, [point])

    async def index_case_async(self, case: CaseInput) -> None:
        await asyncio.to_thread(self.index_case, case)

    def delete_case(self, case_id: str) -> None:
        self._qdrant.delete_by_filter_sync(self._collection, eq_filter("case_id", case_id))
