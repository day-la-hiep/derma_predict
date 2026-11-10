"""Bounded context Khám: lịch hẹn cho một đợt bệnh và lần khám thật."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, model_validator

from app.common.constant import AppointmentStatus, EncounterStatus

if TYPE_CHECKING:
    from app.dto.base.identity import Doctor


class Encounter(BaseModel):
    """Lần khám thật, tạo khi bác sĩ bấm "Bắt đầu khám"; kết luận trỏ tới nó qua `FinalizeReport.encounter`."""

    id: str
    doctor: Doctor | None = None
    status: EncounterStatus = EncounterStatus.OPEN
    opened_at: datetime
    closed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_status(self):
        if self.status == EncounterStatus.CLOSED and self.closed_at is None:
            raise ValueError("closed_at is required when status is closed")
        return self


class Appointment(BaseModel):
    """Lịch hẹn cho một đợt đã đủ thông tin (`ClinicalEpisode.appointments`); không có khám vãng lai."""

    id: str
    doctor: Doctor | None = None  # None tới khi xác nhận
    scheduled_at: datetime
    status: AppointmentStatus = AppointmentStatus.REQUESTED
    reason: str = ""
    cancel_reason: str | None = None
    encounter: Encounter | None = None
    created_at: datetime | None = None

    @model_validator(mode="after")
    def validate_status(self):
        if self.status == AppointmentStatus.CANCELLED and not self.cancel_reason:
            raise ValueError("cancel_reason is required when status is cancelled")
        if self.status not in (AppointmentStatus.REQUESTED, AppointmentStatus.CANCELLED) and self.doctor is None:
            raise ValueError("doctor is required once the appointment is confirmed")
        if self.encounter is not None and self.status not in (AppointmentStatus.IN_PROGRESS, AppointmentStatus.DONE):
            raise ValueError("encounter only exists when the appointment is in_progress or done")
        return self
