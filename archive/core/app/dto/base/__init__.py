"""Entity nghiệp vụ, chia theo bounded context (mỗi context một file):

- `shared`         — File dùng chung
- `identity`       — User / Doctor / Admin, PatientProfile
- `conversation`   — Conversation, Message
- `consultation`   — ConsultationSession, VideoCall (luồng tư vấn cũ)
- `clinical`       — ClinicalFact, ClinicalProvenance
- `episode`        — ClinicalEpisode (đợt bệnh), AiHypothesis, ImagePrediction
- `visit`          — Appointment, Encounter
- `finalize_report` — FinalizeReport (+ snapshot phiếu đã chốt), PatientImage
- `document`       — Document và pipeline ingest

Các context tham chiếu vòng nhau (PatientProfile ↔ ClinicalEpisode ↔ Conversation, FinalizeReport ↔ Encounter), nên
mọi file chỉ import chéo trong `TYPE_CHECKING` và model được rebuild một lần ở đây, không phụ thuộc thứ tự import."""
from app.dto.base.clinical import ClinicalFact, ClinicalProvenance
from app.dto.base.consultation import ConsultationSession, VideoCall
from app.dto.base.conversation import Conversation, Message, MessageMetadata
from app.dto.base.document import (
    Document,
    DocumentChunk,
    DocumentFigure,
    NewDocument,
    DocumentStage,
    DocumentStageOverride,
)
from app.dto.base.identity import Admin, Doctor, PatientProfile, User
from app.dto.base.finalize_report import (
    Assessment,
    FinalizeReport,
    FinalizeReportSnapshot,
    PatientImage,
    SnapshotClinicalFact,
    SnapshotMessage,
    SnapshotPatientProfile,
    SnapshotProvenance,
)
from app.dto.base.episode import AiHypothesis, ClinicalEpisode, HypothesisEvidence, ImagePrediction, LabelScore
from app.dto.base.shared import File
from app.dto.base.visit import Appointment, Encounter

__all__ = [
    "Admin", "AiHypothesis", "Appointment", "Assessment", "ClinicalEpisode", "ClinicalFact", "ClinicalProvenance",
    "ConsultationSession", "Conversation", "Doctor", "Document", "DocumentChunk", "DocumentFigure", "Encounter", "File",
    "FinalizeReport", "FinalizeReportSnapshot", "HypothesisEvidence", "ImagePrediction", "LabelScore", "Message",
    "MessageMetadata", "NewDocument", "PatientImage",
    "PatientProfile", "DocumentStage", "DocumentStageOverride", "SnapshotClinicalFact",
    "SnapshotMessage", "SnapshotPatientProfile", "SnapshotProvenance", "User", "VideoCall",
]

_types_namespace = {name: globals()[name] for name in __all__}
for _name in __all__:
    getattr(globals()[_name], "model_rebuild")(_types_namespace=_types_namespace)
