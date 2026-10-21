"""Service lập chỉ mục và tìm kiếm ca bệnh thực tế (FinalizeReport) trong Qdrant."""

import asyncio
from datetime import UTC, date, datetime
from typing import Any
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
from app.models.finalize_report import FinalizeReport
from app.models.patient_profile import PatientProfile


class FinalizeReportIndexService:
    def __init__(
        self,
        qdrant: QdrantVectorClient,
        embedding: EmbeddingClient,
    ) -> None:
        self._qdrant = qdrant
        self._embedding = embedding
        self._collection = settings.QDRANT_FINALIZE_REPORT_COLLECTION

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

    def build_report_text(
        self,
        report: FinalizeReport,
        profile: PatientProfile | None = None,
        images: list[tuple[Any, Any]] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Tổng hợp thông tin ca bệnh lâm sàng (đã ẩn danh họ tên, sđt) thành văn bản để embedding và payload."""
        snapshot = report.snapshot or {}
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
            f"Chẩn đoán ca bệnh: {report.diagnosis}",
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
        if report.notes:
            lines.append(f"Ghi chú bổ sung: {report.notes}")

        # Ảnh bệnh đã gắn vào báo cáo kết luận (bác sĩ chọn từ đoạn chat) — đưa nhãn + mô tả vào văn bản để semantic search theo ảnh
        image_infos: list[dict[str, Any]] = []
        if images:
            labels: list[str] = []
            for img, f in images:
                confirmed = getattr(img, "confirmed_label", None)
                storage_key = getattr(f, "storage_key", None)
                info = {
                    "confirmed_label": confirmed,
                    "body_site": getattr(img, "body_site", "") or "",
                    "description": getattr(img, "description", "") or "",
                    "storage_key": storage_key,
                    "file_name": getattr(f, "file_name", "") or "",
                }
                image_infos.append(info)
                if confirmed:
                    labels.append(confirmed)
                if info["description"]:
                    labels.append(info["description"])
                if info["body_site"]:
                    labels.append(info["body_site"])
            if labels:
                lines.append("Ảnh bệnh đã lưu: " + "; ".join(dict.fromkeys(labels)))
            if any(i.get("confirmed_label") for i in image_infos):
                lines.append(
                    "Nhãn ảnh xác nhận: "
                    + ", ".join({i["confirmed_label"] for i in image_infos if i.get("confirmed_label")})
                )

        text = "\n".join(lines)

        payload: dict[str, Any] = {
            "case_id": report.id,
            "diagnosis": report.diagnosis,
            "notes": report.notes or "",
            "gender": gender,
            "age": age,
            "allergies": allergies,
            "medical_history": medical_history,
            "clinical_facts": facts,
            "reasoning": reasoning,
            "urgency": urgency,
            "instructions": instructions,
            "is_reference_case": bool(report.is_reference_case),
            "text": text,
            "created_at": report.created_at.isoformat() if report.created_at else None,
            "images": image_infos,
        }
        return text, payload

    def index_report_sync(
        self,
        report: FinalizeReport,
        profile: PatientProfile | None = None,
        images: list[tuple[Any, Any]] | None = None,
    ) -> None:
        """Đồng bộ một ca bệnh vào Qdrant (dùng trong script hoặc thread đồng bộ)."""
        self.ensure_collection()
        text, payload = self.build_report_text(report, profile, images=images)
        vectors, _, _ = self._embedding.embed([text])
        dense_vec = vectors[0]
        sparse_vec = encode_document(text, "mixed")

        point = PointStruct(
            id=self.point_id(report.id),
            vector={"": dense_vec, SPARSE_NAME: sparse_vec},
            payload=payload,
        )
        self._qdrant.upsert_points_sync(self._collection, [point])

    async def index_report(
        self,
        report: FinalizeReport,
        profile: PatientProfile | None = None,
        images: list[tuple[Any, Any]] | None = None,
    ) -> None:
        """Bất đồng bộ nạp ca bệnh vào Qdrant."""
        await asyncio.to_thread(self.index_report_sync, report, profile, images)

    def delete_report_sync(self, case_id: str) -> None:
        """Xoá ca bệnh khỏi Qdrant."""
        self._qdrant.delete_by_filter_sync(
            self._collection,
            eq_filter("case_id", case_id),
        )

    async def delete_report(self, case_id: str) -> None:
        await asyncio.to_thread(self.delete_report_sync, case_id)

    async def search_reports(
        self,
        query: str,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Tìm kiếm ca bệnh tương tự qua dense vector kết hợp lọc điểm."""
        if not await self._qdrant.collection_exists(self._collection):
            return []

        try:
            # Gọi embed query qua embedding model
            vector = await asyncio.to_thread(
                lambda: self._embedding.model.embed_query(query)
            )
            scored_points: list[ScoredPoint] = await self._qdrant.search(
                self._collection,
                vector,
                limit=limit,
            )
        except Exception:  # noqa: BLE001
            # Embedding/DB lỗi (mạng) → fallback: đọc toàn bộ collection và lọc theo từ khoá
            # trong chẩn đoán/nhãn ảnh, để tra cứu vẫn hoạt động offline.
            scored_points = await self._fallback_search(query, limit)

        results: list[dict[str, Any]] = []
        for p in scored_points:
            payload = p.payload or {}
            score = payload.get("_score", getattr(p, "score", 0.0))
            results.append({
                "case_id": payload.get("case_id", str(p.id)),
                "diagnosis": payload.get("diagnosis", ""),
                "score": round(float(score), 3) if score else 0.0,
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
                "images": payload.get("images", []),
            })
        return results

    async def _fallback_search(self, query: str, limit: int) -> list[ScoredPoint]:
        """Fallback không cần embedding: scroll toàn bộ collection, lọc theo từ khoá."""
        try:
            records = await self._qdrant.scroll_all(self._collection)
        except Exception:  # noqa: BLE001
            return []
        q = (query or "").strip().lower()
        scored: list[tuple[float, Any]] = []
        for r in records:
            payload = r.payload or {}
            text = (payload.get("text") or "").lower()
            diagnosis = (payload.get("diagnosis") or "").lower()
            labels = " ".join(
                (img.get("confirmed_label") or "") for img in (payload.get("images") or [])
            ).lower()
            score = 0.0
            if q and q in diagnosis:
                score += 2.0
            if q and q in labels:
                score += 2.0
            if q and q in text:
                score += 1.0
            if score <= 0 and not q:
                score = 0.5
            if score > 0 or not q:
                scored.append((score, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for score, r in scored[:limit]:
            # gắn score vào payload? ScoredPoint có score field; r là Record. Chuyển sang ScoredPoint-like? 
            # search_reports đọc p.payload và p.score. Record không có score. Set attribute.
            payload = r.payload if isinstance(r.payload, dict) else {}
            payload["_score"] = score
            r.payload = payload
            out.append(r)
        return out
