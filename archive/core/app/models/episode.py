"""ClinicalEpisode / AiHypothesis"""
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ClinicalEpisode(Base):
    __tablename__ = "clinical_episodes"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'in_exam', 'closed', 'expired')", name="status_valid"),
        CheckConstraint("status IN ('open', 'in_exam') OR closed_at IS NOT NULL", name="closed_at_when_closed"),
        # mỗi vùng tối đa 1 đợt đang hoạt động: nhiều hội thoại cùng cập nhật một đợt
        Index(
            "uq_clinical_episodes_active_site",
            "patient_profile_id",
            "body_site",
            unique=True,
            postgresql_where=text("status IN ('open', 'in_exam')"),
            sqlite_where=text("status IN ('open', 'in_exam')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default=text("gen_random_uuid()"))  # DB sinh
    patient_profile_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id", ondelete="CASCADE"), index=True)
    body_site: Mapped[str] = mapped_column(String(16))  # `BodySite`
    status: Mapped[str] = mapped_column(String(16), default="open", server_default="open")  # `EpisodeStatus`
    last_conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), default=None
    )
    summary: Mapped[str] = mapped_column(Text, default="", server_default="")  # báo cáo trước khám
    summary_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    urgency: Mapped[str | None] = mapped_column(String(16), default=None)
    red_flags: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    # [{file_id, top_k: [{label, score}]}] — kết quả CNN theo ảnh, thay fact image_finding
    image_predictions: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    model_version: Mapped[str] = mapped_column(String(64), default="", server_default="")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class AiHypothesis(Base):
    __tablename__ = "ai_hypotheses"
    __table_args__ = (
        CheckConstraint("rank >= 1", name="rank_positive"),
        Index("uq_ai_hypotheses_episode_rank", "episode_id", "rank", unique=True),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default=text("gen_random_uuid()"))  # DB sinh
    episode_id: Mapped[str] = mapped_column(ForeignKey("clinical_episodes.id", ondelete="CASCADE"))
    rank: Mapped[int] = mapped_column(Integer)
    diagnosis_code: Mapped[str] = mapped_column(String(64))  # `DiagnosisCode`
    disease: Mapped[str] = mapped_column(String(255))
    confidence: Mapped[str] = mapped_column(String(8))  # `HypothesisConfidence`
    evidence: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    missing: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
