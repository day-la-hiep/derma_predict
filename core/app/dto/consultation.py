"""DTO cho resource Consultation và Pre-consultation Report."""
from pydantic import BaseModel, Field, field_validator


class PatientProfileDto(BaseModel):
    id: str
    full_name: str
    dob: str
    gender: str
    relationship: str = "self"
    phone: str | None = None
    allergies: str = ""
    medical_history: str = ""


class ClinicalFactSourceMessageOutput(BaseModel):
    id: str
    sender: str
    content: str
    created_at: str | None = None


class ClinicalFactOutput(BaseModel):
    id: str
    template_label: str
    fact_type: str
    detail: str
    status: str
    created_at: str
    source_message_ids: list[str] = []
    source_messages: list[ClinicalFactSourceMessageOutput] = []


class PreConsultationReportOutput(BaseModel):
    id: str
    summary: str
    created_at: str


class ConsultationSessionOutput(BaseModel):
    id: str
    conversation_id: str
    conversation_title: str
    patient: PatientProfileDto
    doctor_id: str | None = None
    status: str
    reason: str
    requested_at: str
    started_at: str | None = None
    resolved_at: str | None = None
    report: PreConsultationReportOutput | None = None
    clinical_facts: list[ClinicalFactOutput] = []


class RequestConsultationInput(BaseModel):
    # brief ngắn bệnh nhân nhập; làm tiêu đề ca trong danh sách của bác sĩ
    reason: str = Field(min_length=1, max_length=200)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Vui lòng nhập mô tả ngắn lý do cần bác sĩ tư vấn.")
        return v


class DoctorReplyInput(BaseModel):
    content: str
