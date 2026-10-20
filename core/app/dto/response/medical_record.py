"""DTO Output bệnh án phía bác sĩ — khác `response/patient_profile.py::MedicalRecordOutput` (giấu `is_reference_case`
và snapshot với bệnh nhân)."""
from pydantic import BaseModel

from app.common.constant import ClinicalFactType, FactOrigin
from app.dto.base import MedicalRecordSnapshot, PatientImage, SnapshotClinicalFact, SnapshotMessage
from app.dto.common import FileDto
from app.dto.consultation import PatientProfileDto


# Snapshot lưu storage_key; trên wire thay file bằng `FileDto` có URL tạm để FE hiển thị ảnh
class SnapshotMessageOutput(SnapshotMessage):
    files: list[FileDto] = []


class SnapshotProvenanceOutput(BaseModel):
    message: SnapshotMessageOutput


class SnapshotClinicalFactOutput(SnapshotClinicalFact):
    provenances: list[SnapshotProvenanceOutput] = []


class MedicalRecordSnapshotOutput(MedicalRecordSnapshot):
    clinical_facts: list[SnapshotClinicalFactOutput] = []


class PatientImageOutput(BaseModel):
    id: str
    file: FileDto
    body_site: str = ""
    description: str = ""
    confirmed_label: str | None = None
    captured_at: str | None = None


class DoctorMedicalRecordOutput(BaseModel):
    id: str
    diagnosis: str
    notes: str
    is_reference_case: bool
    doctor_name: str | None = None
    created_at: str
    consultation_session_id: str | None = None
    conversation_id: str | None = None
    snapshot: MedicalRecordSnapshotOutput | None = None
    images: list[PatientImageOutput] = []


class DoctorMedicalRecordItemOutput(DoctorMedicalRecordOutput):
    patient: PatientProfileDto


class DraftFactOutput(BaseModel):
    """Một dòng điền sẵn trong form chốt: fact đang hiệu lực của bệnh nhân kèm nguồn."""

    source_fact_id: str
    fact_type: ClinicalFactType
    label: str
    detail: str
    origin: FactOrigin
    provenances: list[SnapshotProvenanceOutput] = []


class FinalizeDraftOutput(BaseModel):
    patient: PatientProfileDto
    facts: list[DraftFactOutput]
