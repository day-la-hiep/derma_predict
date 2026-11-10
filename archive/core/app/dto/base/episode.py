"""Bounded context Đợt bệnh: vấn đề = (hồ sơ, vùng, đợt) — giả thuyết AI, fact theo đợt, báo cáo trước khám."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, model_validator

from app.common.constant import (
    LONG_TERM_FACT_TYPES,
    BodySite,
    DiagnosisCode,
    EpisodeStatus,
    HypothesisConfidence,
    Urgency,
)

if TYPE_CHECKING:
    from app.dto.base.clinical import ClinicalFact
    from app.dto.base.conversation import Conversation
    from app.dto.base.shared import File
    from app.dto.base.visit import Appointment


class LabelScore(BaseModel):
    label: DiagnosisCode
    score: float


class ImagePrediction(BaseModel):
    file: File
    top_k: list[LabelScore]


class HypothesisEvidence(BaseModel):
    # mã E# của `reflect` chỉ có nghĩa trong lượt, nên lưu nội dung đã giải mã
    source: str
    text: str


class AiHypothesis(BaseModel):
    rank: int = Field(ge=1)
    diagnosis_code: DiagnosisCode  # để so tự động với `FinalizeReport.diagnosis_code`
    disease: str  # tên hiển thị
    confidence: HypothesisConfidence
    evidence: list[HypothesisEvidence] = []
    missing: list[str] = []  # điều còn thiếu để xác nhận / loại trừ


class ClinicalEpisode(BaseModel):
    """Một đợt bệnh ở một vùng; nhiều hội thoại cùng cập nhật. Bệnh nhân không thấy giả thuyết."""

    id: str
    body_site: BodySite
    status: EpisodeStatus = EpisodeStatus.OPEN
    summary: str = ""  # báo cáo trước khám
    summary_at: datetime | None = None
    urgency: Urgency | None = None
    red_flags: list[str] = []
    hypotheses: list[AiHypothesis] = []  # khoá từ `in_exam`
    image_predictions: list[ImagePrediction] = []
    facts: list[ClinicalFact] = []  # triệu chứng / tổn thương của đợt; fact dài hạn ở `PatientProfile.clinical_facts`
    appointments: list[Appointment] = []
    last_conversation: Conversation | None = None
    model_version: str = ""
    opened_at: datetime | None = None
    updated_at: datetime | None = None
    closed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_episode(self):
        if self.status in (EpisodeStatus.CLOSED, EpisodeStatus.EXPIRED) and self.closed_at is None:
            raise ValueError("closed_at is required when status is closed or expired")
        if any(f.fact_type in LONG_TERM_FACT_TYPES for f in self.facts):
            raise ValueError("long-term facts (allergy/history/medication) belong to PatientProfile, not an episode")
        ranks = [h.rank for h in self.hypotheses]
        if len(ranks) != len(set(ranks)):
            raise ValueError("hypothesis ranks must be unique")
        return self
