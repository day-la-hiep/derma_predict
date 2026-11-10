"""Body của `POST /internal/turns` (consultation -> agent): mở turn mới (`type="turn"`) hoặc sinh báo cáo tiền tư vấn (`type="consultation_report"`). Kết quả không nằm ở đây: agent tự gọi
consultation (`/internal/turns/{id}/result`) và clinical (`apply-turn`, `consultation-reports`), xem services/contracts/README.md."""
from typing import Literal

from pydantic import BaseModel


class TurnAttachment(BaseModel):
    """1 ảnh đính kèm turn — field khớp entity `File`; `storage_key` là key MinIO
    (bucket ảnh đính kèm), agent tự fetch bytes qua `get_object_bytes()` khi
    tool `classify_skin_image` (`agent/tools/skin_image/classifier.py`) cần."""

    file_name: str
    content_type: str
    storage_key: str


class TurnRequest(BaseModel):
    type: Literal["turn", "consultation_report"]
    conversation_id: str
    message_id: str  # id assistant message của turn hoặc marker message
    # id tin người dùng trong DB (type="turn"): gán cho HumanMessage để nguồn của fact trỏ đúng bảng `messages`
    user_message_id: str | None = None
    corr_id: str | None = None
    content: str | None = None  # bắt buộc khi type="turn"
    attached_files: list[TurnAttachment] | None = None
    # Trường dành cho consultation_report:
    session_id: str | None = None
    patient_profile_id: str | None = None
    reason: str | None = None
