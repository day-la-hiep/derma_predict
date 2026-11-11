"""Appointment / Encounter"""
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

ACTIVE_APPOINTMENT = "status IN ('requested', 'confirmed', 'in_progress')"


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('requested', 'confirmed', 'in_progress', 'done', 'cancelled', 'no_show')", name="status_valid"
        ),
        CheckConstraint("status <> 'cancelled' OR cancel_reason IS NOT NULL", name="cancel_reason_when_cancelled"),
        CheckConstraint("status IN ('requested', 'cancelled') OR doctor_id IS NOT NULL", name="doctor_when_confirmed"),
        # mỗi đợt tối đa 1 lịch hẹn còn hiệu lực
        Index(
            "uq_appointments_active_episode",
            "episode_id",
            unique=True,
            postgresql_where=text(ACTIVE_APPOINTMENT),
            sqlite_where=text(ACTIVE_APPOINTMENT),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default=text("gen_random_uuid()"))  # DB sinh
    patient_profile_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id", ondelete="CASCADE"), index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("clinical_episodes.id", ondelete="CASCADE"), index=True)
    doctor_id: Mapped[str | None] = mapped_column(ForeignKey("doctors.user_id", ondelete="SET NULL"), default=None)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(16), default="requested", server_default="requested")  # `AppointmentStatus`
    reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    cancel_reason: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class Encounter(Base):
    __tablename__ = "encounters"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'closed')", name="status_valid"),
        CheckConstraint("status <> 'closed' OR closed_at IS NOT NULL", name="closed_at_when_closed"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default=text("gen_random_uuid()"))  # DB sinh
    # lần khám luôn bắt đầu từ lịch hẹn
    appointment_id: Mapped[str] = mapped_column(ForeignKey("appointments.id", ondelete="CASCADE"), unique=True)
    patient_profile_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id", ondelete="CASCADE"), index=True)
    doctor_id: Mapped[str | None] = mapped_column(ForeignKey("doctors.user_id", ondelete="SET NULL"), default=None)
    status: Mapped[str] = mapped_column(String(8), default="open", server_default="open")  # `EncounterStatus`
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
