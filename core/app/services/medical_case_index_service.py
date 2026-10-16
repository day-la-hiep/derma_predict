"""Service lập chỉ mục và tìm kiếm ca bệnh thực tế (MedicalRecord) trong Qdrant."""

import asyncio
from datetime import UTC, date, datetime
from typing import Any
import uuid

from qdrant_client.models import (
    Distance,
    Filter,
    FilterSelector,
    Modifier,
    PointStruct,
    ScoredPoint,
    SparseVectorParams,
    VectorParams,
)

from app.config.settings import settings
from app.infra.bm25 import SPARSE_NAME, encode_document, encode_query
from app.infra.embedding_client import EmbeddingClient
from app.infra.qdrant_client import QdrantVectorClient, eq_filter
from app.models.medical_record import MedicalRecord
from app.models.patient_profile import PatientProfile


class MedicalCaseIndexService:
    def __init__(
        self,
        qdrant: QdrantVectorClient,
        embedding: EmbeddingClient,
    ) -> None:
        self._qdrant = qdrant
        self._embedding = embedding
        self._collection = settings.QDRANT_MEDICAL_CASE_COLLECTION

    @property
    def collection(self) -> str:
        return self._collection

    @staticmethod
    def point_id(case_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"case:{case_id}"))

    def ensure_collection(self) -> None:
        """Đảm bảo collection ca bệnh đã được tạo trong Qdrant kèm vector dense và sparse."""
        self._qdrant.ensure_collection_sync(
            self._collection,
            settings.EMBEDDING_DIM,
            keyword_index_fields=("case_id", "is_reference_case", "diagnosis"),
            sparse_names=(SPARSE_NAME,),
        )

    def build_case_text(
        self,
        record: MedicalRecord,
        profile: PatientProfile | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Tổng hợp thông tin ca bệnh lâm sàng (đã ẩn danh họ tên, sđt) thành văn bản để embedding và payload."""
        snapshot = record.snapshot or {}
        p_profile = snapshot.get("patient_profile") or {}
        assessment = snapshot.get("assessment") or {}
        facts = snapshot.get("clinical_facts") or []

        # Giới tính, tuổi, tiền sử (không đưa tên thật hoặc sđt để bảo mật danh tính bệnh nhân)
        gender = p_profile.get("gender") or (profile.gender if profile else "")
        dob_val = p_profile.get("dob") or (profile.dob if profile else None)
        age: int | None = None
        if dob_val:
            try:
                if isinstance(dob_val, str):
                    dob_year = int(dob_val.split("-")[0])
                elif isinstance(dob_val, (date, datetime)):
                    dob_year = dob_val.year
                else:
                    dob_year = None
                if dob_year:
                    age = max(datetime.now(UTC).year - dob_year, 0)
            except Exception:  # noqa: BLE001
                age = None

        allergies = p_profile.get("allergies") or (profile.allergies if profile else "")
        medical_history = p_profile.get("medical_history") or (profile.medical_history if profile else "")

        reasoning = assessment.get("reasoning", "")
        urgency = assessment.get("urgency", "")
        instructions = assessment.get("instructions", [])

        lines: list[str] = [
            f"Chẩn đoán ca bệnh: {record.diagnosis}",
        ]

        patient_traits: list[str] = []
        if gender:
            patient_traits.append(f"Giới tính: {gender}")
        if age is not None:
            patient_traits.append(f"Tuổi: {age}")
        if medical_history:
            patient_traits.append(f"Tiền sử bệnh: {medical_history}")
        if allergies:
            patient_traits.append(f"Tiền sử dị ứng: {allergies}")
        if patient_traits:
            lines.append(f"Đặc điểm bệnh nhân: {', '.join(patient_traits)}")

        if facts:
            lines.append("Dữ kiện lâm sàng & Triệu chứng ghi nhận:")
            for f in facts:
                f_type = f.get("fact_type", "symptom")
                label = f.get("label", "")
                detail = f.get("detail", "")
                lines.append(f"- [{f_type}] {label}: {detail}")

        if reasoning:
            lines.append(f"Đánh giá & Cơ sở chẩn đoán của bác sĩ: {reasoning}")
        if urgency:
            lines.append(f"Mức độ khẩn cấp: {urgency}")
        if instructions:
            inst_text = "; ".join(instructions) if isinstance(instructions, list) else str(instructions)
            lines.append(f"Dặn dò & Hướng xử trí: {inst_text}")
        if record.notes:
            lines.append(f"Ghi chú bổ sung: {record.notes}")

        text = "\n".join(lines)

        payload: dict[str, Any] = {
            "case_id": record.id,
            "diagnosis": record.diagnosis,
            "notes": record.notes or "",
            "gender": gender,
            "age": age,
            "allergies": allergies,
            "medical_history": medical_history,
            "clinical_facts": facts,
            "reasoning": reasoning,
            "urgency": urgency,
            "instructions": instructions,
            "is_reference_case": bool(record.is_reference_case),
            "text": text,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }
        return text, payload

    def index_record_sync(
        self,
        record: MedicalRecord,
        profile: PatientProfile | None = None,
    ) -> None:
        """Đồng bộ một ca bệnh vào Qdrant (dùng trong script hoặc thread đồng bộ)."""
        self.ensure_collection()
        text, payload = self.build_case_text(record, profile)
        vectors, _, _ = self._embedding.embed([text])
        dense_vec = vectors[0]
        sparse_vec = encode_document(text, "mixed")

        point = PointStruct(
            id=self.point_id(record.id),
            vector={"": dense_vec, SPARSE_NAME: sparse_vec},
            payload=payload,
        )
        self._qdrant.upsert_points_sync(self._collection, [point])

    async def index_record(
        self,
        record: MedicalRecord,
        profile: PatientProfile | None = None,
    ) -> None:
        """Bất đồng bộ nạp ca bệnh vào Qdrant."""
        await asyncio.to_thread(self.index_record_sync, record, profile)

    def delete_record_sync(self, case_id: str) -> None:
        """Xoá ca bệnh khỏi Qdrant."""
        self._qdrant.delete_by_filter_sync(
            self._collection,
            eq_filter("case_id", case_id),
        )

    async def delete_record(self, case_id: str) -> None:
        await asyncio.to_thread(self.delete_record_sync, case_id)

    async def search_cases(
        self,
        query: str,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Tìm kiếm ca bệnh tương tự qua dense vector kết hợp lọc điểm."""
        if not await self._qdrant.collection_exists(self._collection):
            return []

        # Gọi embed query qua embedding model
        vector = await asyncio.to_thread(
            lambda: self._embedding.model.embed_query(query)
        )
        scored_points: list[ScoredPoint] = await self._qdrant.search(
            self._collection,
            vector,
            limit=limit,
        )

        results: list[dict[str, Any]] = []
        for p in scored_points:
            payload = p.payload or {}
            results.append({
                "case_id": payload.get("case_id", str(p.id)),
                "diagnosis": payload.get("diagnosis", ""),
                "score": round(float(p.score), 3),
                "gender": payload.get("gender"),
                "age": payload.get("age"),
                "allergies": payload.get("allergies"),
                "medical_history": payload.get("medical_history"),
                "clinical_facts": payload.get("clinical_facts", []),
                "doctor_reasoning": payload.get("reasoning", ""),
                "urgency": payload.get("urgency", ""),
                "treatment_instructions": payload.get("instructions", []),
                "doctor_notes": payload.get("notes", ""),
                "summary": payload.get("text", ""),
            })
        return results
