"""DTO Input cho lịch hẹn và lần khám."""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class BookAppointmentInput(BaseModel):
    patient_profile_id: str
    episode_id: str
    scheduled_at: datetime
    reason: str = Field(default="", max_length=500)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, v: str) -> str:
        return v.strip()


class CancelAppointmentInput(BaseModel):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Vui lòng nhập lý do huỷ.")
        return v


class ChangeEpisodeInput(BaseModel):
    episode_id: str
