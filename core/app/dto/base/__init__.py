"""Entity nghiệp vụ, chia theo bounded context (mỗi context một file):

- `shared`         — File dùng chung
- `identity`       — User / Doctor / Admin, PatientProfile
- `conversation`   — Conversation, Message
- `consultation`   — ConsultationSession, VideoCall, PreConsultationReport
- `clinical`       — ClinicalFactTemplate, ClinicalFact
- `finalize_report` — FinalizeReport (+ snapshot phiếu đã chốt), PatientImage
- `document`       — Document và pipeline ingest

Các context tham chiếu vòng nhau (Conversation ↔ ConsultationSession ↔ ClinicalFact, PatientProfile ↔ FinalizeReport), nên
mọi file chỉ import chéo trong `TYPE_CHECKING` và model được rebuild một lần ở đây, không phụ thuộc thứ tự import."""
from app.dto.base.clinical import ClinicalFact, ClinicalFactTemplate, ClinicalProvenance
from app.dto.base.consultation import ConsultationSession, PreConsultationReport, VideoCall
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
from app.dto.base.shared import File

__all__ = [
    "Admin", "Assessment", "ClinicalFact", "ClinicalFactTemplate", "ClinicalProvenance", "ConsultationSession",
    "Conversation", "Doctor", "Document", "DocumentChunk", "DocumentFigure", "File",
    "FinalizeReport", "FinalizeReportSnapshot", "Message", "MessageMetadata", "NewDocument", "PatientImage",
    "PatientProfile", "PreConsultationReport", "DocumentStage", "DocumentStageOverride", "SnapshotClinicalFact",
    "SnapshotMessage", "SnapshotPatientProfile", "SnapshotProvenance", "User", "VideoCall",
]

_types_namespace = {name: globals()[name] for name in __all__}
for _name in __all__:
    getattr(globals()[_name], "model_rebuild")(_types_namespace=_types_namespace)
