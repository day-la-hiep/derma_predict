from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PatientProfile(Base):
    __tablename__ = "patient_profiles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default=text("gen_random_uuid()"))  # DB sinh
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    dob: Mapped[date] = mapped_column(Date)
    gender: Mapped[str] = mapped_column(String(16))  # `Gender`
    # `ProfileRelationship`; server_default để hồ sơ có trước khi thêm cột vẫn hợp lệ
    relationship: Mapped[str] = mapped_column(String(16), default="self", server_default="self")
    phone: Mapped[str | None] = mapped_column(String(32), default=None)
    allergies: Mapped[str] = mapped_column(Text, default="", server_default="")
    medical_history: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
