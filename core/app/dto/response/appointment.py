"""DTO Output cho lịch hẹn và lần khám. Bệnh nhân không nhận giả thuyết AI; bác sĩ nhận kèm lời nhắc chưa phải chẩn đoán."""
from pydantic import BaseModel

from app.dto.common import FileDto
from app.dto.consultation import ClinicalFactOutput, PatientProfileDto

AI_DISCLAIMER = "Gợi ý của AI để hỗ trợ bác sĩ, không phải chẩn đoán y khoa."


class AppointmentOutput(BaseModel):
    id: str
    patient_profile_id: str
    episode_id: str
    body_site: str
    body_site_label: str
    doctor_id: str | None = None
    doctor_name: str | None = None
    scheduled_at: str
    status: str
    reason: str
    cancel_reason: str | None = None
    created_at: str
    encounter_id: str | None = None


class PatientEpisodeOutput(BaseModel):
    """Đợt đang theo dõi, góc nhìn bệnh nhân: không có giả thuyết."""

    id: str
    body_site: str
    body_site_label: str
    status: str
    updated_at: str
    facts: list[str] = []
    bookable: bool
    not_bookable_reason: str | None = None
    appointment: AppointmentOutput | None = None


class HypothesisEvidenceOutput(BaseModel):
    source: str
    text: str


class HypothesisOutput(BaseModel):
    rank: int
    diagnosis_code: str
    diagnosis_label: str
    disease: str
    confidence: str
    evidence: list[HypothesisEvidenceOutput] = []
    missing: list[str] = []


class LabelScoreOutput(BaseModel):
    label: str
    label_name: str
    score: float


class ImagePredictionOutput(BaseModel):
    file_id: str
    file: FileDto | None = None
    top_k: list[LabelScoreOutput] = []


class DoctorEpisodeOutput(BaseModel):
    id: str
    body_site: str
    body_site_label: str
    status: str
    summary: str
    summary_at: str | None = None
    urgency: str | None = None
    red_flags: list[str] = []
    hypotheses: list[HypothesisOutput] = []
    hypotheses_locked: bool
    facts: list[ClinicalFactOutput] = []
    image_predictions: list[ImagePredictionOutput] = []
    updated_at: str
    disclaimer: str = AI_DISCLAIMER


class DoctorAppointmentItemOutput(AppointmentOutput):
    patient: PatientProfileDto
    top_hypothesis: str | None = None


class DoctorAppointmentDetailOutput(DoctorAppointmentItemOutput):
    episode: DoctorEpisodeOutput
    long_term_facts: list[ClinicalFactOutput] = []
    other_episodes: list[PatientEpisodeOutput] = []  # đợt khác của hồ sơ, để đổi đợt trước khi khám
