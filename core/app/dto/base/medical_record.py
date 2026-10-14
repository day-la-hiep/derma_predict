"""Bounded context Bệnh án: bệnh án do bác sĩ ghi và ảnh bệnh kèm theo."""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.common.constant import ClinicalFactType, FactOrigin, Gender, MessageSender, ProfileRelationship, Urgency

if TYPE_CHECKING:
    from app.dto.base.consultation import ConsultationSession
    from app.dto.base.identity import Doctor
    from app.dto.base.shared import File


class MedicalRecord(BaseModel):
    """Phiếu bệnh án bác sĩ chốt sau một lần khám hoặc tư vấn (`PatientProfile.medical_records`). Không sửa sau khi chốt."""

    id: str
    diagnosis: str  # nhận định của bác sĩ
    notes: str = ""  # ghi chú chung (hướng điều trị, tái khám) — bệnh nhân cũng xem được
    doctor: Doctor | None = None
    consultation_session: ConsultationSession | None = None  # ca tư vấn gốc; None = khám trực tiếp
    snapshot: MedicalRecordSnapshot | None = None  # None với bệnh án ghi trước khi có snapshot
    images: list[PatientImage] = []
    # ca bệnh tham khảo: bác sĩ xác nhận dùng làm dữ liệu cho KB / chatbot tra ca tương tự (ẩn định danh khi đưa vào KB)
    is_reference_case: bool = False
    created_at: datetime | None = None  # thời điểm chốt


class MedicalRecordSnapshot(BaseModel):
    """Bản chụp bất biến của kết quả bác sĩ đã sửa và chốt. Phiếu hiển thị hoàn toàn từ đây, không đọc lại hồ sơ/dữ kiện
    đang sống — bệnh nhân sửa dị ứng hay fact bị thay sau này thì phiếu vẫn giữ đúng nội dung lúc chốt."""

    patient_profile: SnapshotPatientProfile
    assessment: Assessment
    clinical_facts: list[SnapshotClinicalFact] = []


class SnapshotPatientProfile(BaseModel):
    full_name: str
    dob: date
    gender: Gender
    relationship: ProfileRelationship = ProfileRelationship.SELF
    phone: str | None = None
    allergies: str = ""
    medical_history: str = ""


class Assessment(BaseModel):
    reasoning: str = ""  # cơ sở dẫn tới nhận định — chỉ bác sĩ xem
    urgency: Urgency
    instructions: list[str] = []  # dặn dò bệnh nhân


class SnapshotClinicalFact(BaseModel):
    fact_type: ClinicalFactType
    label: str
    detail: str = ""
    origin: FactOrigin
    # bằng chứng chép nguyên từ tin gốc lúc chốt; rỗng khi không có tin gốc (bác sĩ tự ghi, tin đã xoá, fact cũ)
    provenances: list[SnapshotProvenance] = []


class SnapshotProvenance(BaseModel):
    message: SnapshotMessage


class SnapshotMessage(BaseModel):
    id: str  # để nhảy tới tin trong luồng hội thoại gốc; nội dung đã chép nên tin bị xoá vẫn đọc được
    sender: MessageSender
    content: str = ""
    created_at: datetime | None = None
    files: list[File] = []  # lưu storage_key, URL tải sinh lại lúc đọc vì presigned URL hết hạn


class PatientImage(BaseModel):
    """Ảnh bệnh được bác sĩ gắn vào bệnh án. `file` có thể dùng lại file bệnh nhân đã gửi trong chat (cùng dòng `files`)."""

    id: str
    file: File
    body_site: str = ""  # vị trí trên cơ thể
    description: str = ""
    confirmed_label: str | None = None  # nhãn bác sĩ xác nhận — dữ liệu huấn luyện CNN
    captured_at: datetime | None = None
