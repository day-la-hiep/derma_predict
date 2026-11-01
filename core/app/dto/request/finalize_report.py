"""DTO Input cho báo cáo kết luận do bác sĩ chốt."""

from pydantic import BaseModel, Field

from app.common.constant import ClinicalFactType, Urgency


class FactInput(BaseModel):
    """Dữ kiện trong form chốt. Client không gửi nguồn: server tự chép tin gốc từ `source_fact_id` lúc chốt."""

    source_fact_id: str | None = None  # fact trích từ hội thoại mà dòng này dựa vào; None = bác sĩ tự ghi
    fact_type: ClinicalFactType
    label: str = Field(min_length=1, max_length=255)
    detail: str = ""


class PatientImageInput(BaseModel):
    """Ảnh bệnh bác sĩ chọn từ đoạn chat để gắn vào báo cáo kết luận (file đã nằm trong `files`/MinIO)."""

    file_id: str = Field(min_length=1)
    body_site: str = ""
    description: str = ""
    confirmed_label: str | None = None  # nhãn bác sĩ xác nhận — nên khớp 22 lớp CNN


class FinalizeReportInput(BaseModel):
    diagnosis: str = Field(min_length=1)
    notes: str = ""
    is_reference_case: bool = False
    reasoning: str = ""
    urgency: Urgency
    instructions: list[str] = []
    facts: list[FactInput] = []
    images: list[PatientImageInput] = []

