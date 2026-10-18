"""DTO Output cho resource Patient Profile"""

from pydantic import BaseModel


class PatientProfileOutput(BaseModel):
    id: str
    full_name: str
    dob: str
    gender: str
    relationship: str
    phone: str | None = None
    allergies: str
    medical_history: str
    created_at: str


class MedicalRecordOutput(BaseModel):
    # không trả `is_reference_case`: cờ nội bộ của bác sĩ
    id: str
    diagnosis: str
    notes: str
    doctor_name: str | None = None
    created_at: str
