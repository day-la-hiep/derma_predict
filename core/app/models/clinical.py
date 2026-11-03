"""ClinicalFact / ClinicalProvenance / PreConsultationReport"""
from datetime import UTC, datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ClinicalFact(Base):
    __tablename__ = "clinical_facts"
    __table_args__ = (
        CheckConstraint(
            "fact_type IN ('symptom', 'lesion', 'history', 'medication', 'allergy', 'other')", name="fact_type_valid"
        ),
        CheckConstraint(
            "(fact_type IN ('allergy', 'history', 'medication')) = (episode_id IS NULL)", name="long_term_no_episode"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default=text("gen_random_uuid()"))  # DB sinh
    # fact thuộc về người bệnh, không thuộc một cuộc chat; hội thoại sinh ra fact truy ngược qua `ClinicalProvenance`
    patient_profile_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id", ondelete="CASCADE"), index=True)
    # NULL = fact dài hạn (allergy / history / medication) của hồ sơ; còn lại thuộc một đợt bệnh
    episode_id: Mapped[str | None] = mapped_column(
        ForeignKey("clinical_episodes.id", ondelete="CASCADE"), index=True, default=None
    )
    fact_type: Mapped[str] = mapped_column(String(32))  # `ClinicalFactType`
    label: Mapped[str] = mapped_column(String(255))
    ontology_id: Mapped[str | None] = mapped_column(String(128), default=None)
    # giá trị hiện tại, sửa tại chỗ; lịch sử nằm ở `clinical_provenances`
    detail: Mapped[str] = mapped_column(Text, default="", server_default="")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    verified_by_id: Mapped[str | None] = mapped_column(ForeignKey("doctors.user_id", ondelete="SET NULL"), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


# Bảng fact là hiện trạng: mỗi (phạm vi, loại, nhãn) một dòng, nhãn so không phân biệt hoa thường.
# Phạm vi của fact dài hạn là hồ sơ, của fact theo đợt là đợt — "ngứa" ở mặt và ở chân là 2 dòng.
Index(
    "uq_clinical_facts_long_term",
    ClinicalFact.patient_profile_id,
    ClinicalFact.fact_type,
    func.lower(ClinicalFact.label),
    unique=True,
    postgresql_where=ClinicalFact.episode_id.is_(None),
)
Index(
    "uq_clinical_facts_episode",
    ClinicalFact.episode_id,
    ClinicalFact.fact_type,
    func.lower(ClinicalFact.label),
    unique=True,
    postgresql_where=ClinicalFact.episode_id.is_not(None),
)


class ClinicalProvenance(Base):
    """`ClinicalFact.provenances` — nhật ký chỉ thêm: mỗi dòng là một lần một nguồn ghi nhận giá trị của fact."""

    __tablename__ = "clinical_provenances"
    __table_args__ = (CheckConstraint("kind IN ('chat', 'doctor', 'profile')", name="kind_valid"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default=text("gen_random_uuid()"))  # DB sinh
    fact_id: Mapped[str] = mapped_column(ForeignKey("clinical_facts.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="chat", server_default="chat")  # `ProvenanceKind`
    # SET NULL: xoá hội thoại không làm fact mất bằng chứng vì nội dung đã chép vào `quote`
    message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), index=True, default=None
    )
    quote: Mapped[str] = mapped_column(Text, default="", server_default="")
    doctor_id: Mapped[str | None] = mapped_column(ForeignKey("doctors.user_id", ondelete="SET NULL"), default=None)
    detail: Mapped[str] = mapped_column(Text, default="", server_default="")  # giá trị fact nguồn này ghi nhận
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PreConsultationReport(Base):
    __tablename__ = "pre_consultation_reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default=text("gen_random_uuid()"))  # DB sinh
    # 1 báo cáo / phiên tư vấn
    consultation_session_id: Mapped[str] = mapped_column(
        ForeignKey("consultation_sessions.id", ondelete="CASCADE"), unique=True
    )
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
