from datetime import date, datetime

from pydantic import BaseModel


class CaseImage(BaseModel):
    file_id: str
    storage_key: str
    file_name: str = ""
    body_site: str = ""
    description: str = ""
    confirmed_label: str | None = None


class CasePatient(BaseModel):
    gender: str = ""
    dob: date | None = None
    allergies: str = ""
    medical_history: str = ""


class CaseAssessment(BaseModel):
    reasoning: str = ""
    urgency: str = ""
    instructions: list[str] = []


class CaseFact(BaseModel):
    fact_type: str = "symptom"
    label: str = ""
    detail: str = ""


class CaseSnapshot(BaseModel):
    """Chỉ phần knowledge dùng của `FinalizeReportSnapshot`; trường khác clinical gửi thêm sẽ bị bỏ qua."""

    patient_profile: CasePatient
    assessment: CaseAssessment
    clinical_facts: list[CaseFact] = []


class CaseInput(BaseModel):
    """Báo cáo kết luận đã chốt do clinical gửi sang để index Qdrant (ca tham khảo) và đồng bộ đồ thị bệnh nhân."""

    report_id: str
    patient_profile_id: str
    doctor_id: str | None = None
    encounter_id: str | None = None
    consultation_session_id: str | None = None
    diagnosis: str
    notes: str = ""
    is_reference_case: bool = False
    created_at: datetime
    snapshot: CaseSnapshot
    images: list[CaseImage] = []

    @property
    def visit_id(self) -> str:
        """Id nút phiên trong đồ thị: lần khám, hoặc phiên tư vấn của dữ liệu cũ."""
        return self.encounter_id or self.consultation_session_id or self.report_id
