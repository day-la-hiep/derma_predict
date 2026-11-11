"""DTO Output cho resource Patient Profile"""

from pydantic import BaseModel


class ProfileFactOutput(BaseModel):
    id: str
    fact_type: str
    label: str
    detail: str
    verified_at: str | None = None  # bác sĩ đã xác nhận lúc chốt


class PatientProfileOutput(BaseModel):
    id: str
    full_name: str
    dob: str
    gender: str
    relationship: str
    phone: str | None = None
    long_term_facts: list[ProfileFactOutput] = []  # dị ứng / tiền sử / thuốc, gồm cả mục AI trích từ chat
    created_at: str


class PatientFinalizeReportOutput(BaseModel):
    # không trả `is_reference_case`: cờ nội bộ của bác sĩ
    id: str
    diagnosis: str
    notes: str
    doctor_name: str | None = None
    created_at: str
