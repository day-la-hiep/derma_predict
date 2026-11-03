"""Bounded context Tư vấn bác sĩ (luồng cũ): phiên tư vấn, cuộc gọi video. Báo cáo trước khám nay là `ClinicalEpisode.summary`."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, model_validator

from app.common.constant import ConsultationStatus

if TYPE_CHECKING:
    from app.dto.base.identity import Doctor


class ConsultationSession(BaseModel):
    """Mốc đánh dấu một lần bệnh nhân nhờ bác sĩ hỗ trợ — không chứa tin nhắn. Tin trao đổi nằm trong
    `Conversation.message`; ba mốc yêu cầu/nhận/đóng hiện thành tin `CONSULTATION_*` trong luồng đó.

    Bác sĩ xem được luồng chat từ đầu tới tin `CONSULTATION_RESOLVED` của phiên (phiên còn mở: tới hiện tại)."""

    doctor: Doctor | None = None  # None khi chưa có bác sĩ nhận
    status: ConsultationStatus = ConsultationStatus.PENDING
    reason: str
    requested_at: datetime | None = None
    started_at: datetime | None = None
    resolved_at: datetime | None = None
    video_calls: list[VideoCall] = []  # các cuộc gọi video bác sĩ và bệnh nhân thực hiện trong phiên này

    @model_validator(mode="after")
    def validate_status(self):
        if self.status != ConsultationStatus.PENDING and self.doctor is None:
            raise ValueError("doctor is required when status is active or resolved")
        if self.status == ConsultationStatus.RESOLVED and self.resolved_at is None:
            raise ValueError("resolved_at is required when status is resolved")
        return self


class VideoCall(BaseModel):
    """Một cuộc gọi video diễn ra trong một phiên tư vấn (`ConsultationSession.video_calls`); tin `VIDEO_CALL` trong luồng
    chat chỉ trỏ tới cuộc gọi này."""

    room_id: str
    status: Literal["pending", "ongoing", "ended"]
    started_at: datetime | None = None
    ended_at: datetime | None = None
