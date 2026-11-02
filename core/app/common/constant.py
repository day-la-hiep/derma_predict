from enum import Enum


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"


class ProfileRelationship(str, Enum):
    """Quan hệ của hồ sơ bệnh nhân với chủ tài khoản (một tài khoản quản lý hồ sơ cho cả người nhà)."""

    SELF = "self"
    CHILD = "child"
    PARENT = "parent"
    SPOUSE = "spouse"
    OTHER = "other"


class MessageType(str, Enum):
    TEXT = "text"
    VIDEO_CALL = "video_call"
    ATTACHED = "attached"
    # 3 mốc của một phiên tư vấn bác sĩ, hiện trong luồng chat như tin hệ thống
    CONSULTATION_REQUESTED = "consultation_requested"  # bệnh nhân gửi yêu cầu
    CONSULTATION_ACCEPTED = "consultation_accepted"  # bác sĩ nhận và bắt đầu xử lý
    CONSULTATION_RESOLVED = "consultation_resolved"  # bác sĩ đóng yêu cầu khi xong


class MessageSender(str, Enum):
    """Ai gửi tin. Bác sĩ trả lời ngay trong luồng chat của hội thoại, nên tin phải phân biệt được 3 bên."""

    PATIENT = "patient"
    AI = "ai"
    DOCTOR = "doctor"


class ClinicalFactType(str, Enum):
    SYMPTOM = "symptom"  # triệu chứng cơ năng: ngứa, đau, rát...
    LESION = "lesion"  # tổn thương da: hình thái, vị trí, kích thước
    HISTORY = "history"  # tiền sử bản thân / gia đình, diễn tiến bệnh
    MEDICATION = "medication"  # thuốc đang / đã dùng
    ALLERGY = "allergy"
    IMAGE_FINDING = "image_finding"  # kết quả phân loại ảnh (CNN) — chỉ là giả thuyết
    OTHER = "other"


class Urgency(str, Enum):
    """Mức khẩn cấp bác sĩ chốt cho một lần khám."""

    EMERGENCY = "emergency"  # cần khám ngay
    FEW_DAYS = "few_days"  # khám trong vài ngày
    MONITOR = "monitor"  # theo dõi tại nhà


class FactOrigin(str, Enum):
    """Nguồn gốc của một dữ kiện trong phiếu đã chốt — ghi tường minh, không suy từ việc có/không có tin nhắn nguồn."""

    PATIENT_REPORTED = "patient_reported"  # bệnh nhân tự khai trong hội thoại
    AI_INFERRED = "ai_inferred"  # AI suy ra (vd phân loại ảnh) — chỉ là giả thuyết
    DOCTOR_OBSERVED = "doctor_observed"  # bác sĩ ghi nhận khi khám
    DOCTOR_CORRECTED = "doctor_corrected"  # bác sĩ sửa lại một dữ kiện có sẵn


class ConsultationStatus(str, Enum):
    PENDING = "pending"  # chờ bác sĩ nhận
    ACTIVE = "active"  # bác sĩ đang trao đổi
    RESOLVED = "resolved"  # bác sĩ đã đánh dấu xử lý xong


class BodySite(str, Enum):
    """Vùng của một đợt bệnh. Danh mục cố định để LLM chọn, tránh "má" và "mặt" thành 2 đợt."""

    DAU_MAT = "dau_mat"
    DA_DAU_TOC = "da_dau_toc"
    CO = "co"
    THAN_TRUOC = "than_truoc"
    LUNG = "lung"
    TAY = "tay"
    BAN_TAY = "ban_tay"
    CHAN = "chan"
    BAN_CHAN = "ban_chan"
    SINH_DUC = "sinh_duc"
    MONG = "mong"
    NHIEU_VUNG = "nhieu_vung"  # cùng một bệnh ở nhiều chỗ, vd vảy nến khuỷu tay + đầu gối


BODY_SITE_LABELS: dict[BodySite, str] = {
    BodySite.DAU_MAT: "Đầu, mặt",
    BodySite.DA_DAU_TOC: "Da đầu, tóc",
    BodySite.CO: "Cổ",
    BodySite.THAN_TRUOC: "Ngực, bụng",
    BodySite.LUNG: "Lưng",
    BodySite.TAY: "Tay",
    BodySite.BAN_TAY: "Bàn tay",
    BodySite.CHAN: "Chân",
    BodySite.BAN_CHAN: "Bàn chân",
    BodySite.SINH_DUC: "Vùng sinh dục",
    BodySite.MONG: "Móng",
    BodySite.NHIEU_VUNG: "Nhiều vùng",
}


class DiagnosisCode(str, Enum):
    """Mã chẩn đoán dùng chung cho giả thuyết AI và kết luận bác sĩ, để so được với nhau. Giá trị trùng tên lớp của checkpoint CNN."""

    ACNE = "Acne"
    ACTINIC_KERATOSIS = "Actinic_Keratosis"
    BENIGN_TUMORS = "Benign_tumors"
    BULLOUS = "Bullous"
    CANDIDIASIS = "Candidiasis"
    DRUG_ERUPTION = "DrugEruption"
    ECZEMA = "Eczema"
    INFESTATIONS_BITES = "Infestations_Bites"
    LICHEN = "Lichen"
    LUPUS = "Lupus"
    MOLES = "Moles"
    PSORIASIS = "Psoriasis"
    ROSACEA = "Rosacea"
    SEBORRH_KERATOSES = "Seborrh_Keratoses"
    SKIN_CANCER = "SkinCancer"
    SUN_DAMAGE = "Sun_Sunlight_Damage"
    TINEA = "Tinea"
    UNKNOWN_NORMAL = "Unknown_Normal"  # da bình thường / không rõ tổn thương — khác OTHER (có bệnh nhưng ngoài danh mục)
    VASCULAR_TUMORS = "Vascular_Tumors"
    VASCULITIS = "Vasculitis"
    VITILIGO = "Vitiligo"
    WARTS = "Warts"
    OTHER = "OTHER"  # bệnh ngoài danh mục, kèm mô tả tự do; hai bên cùng OTHER không tính là trúng


DIAGNOSIS_CODE_LABELS: dict[DiagnosisCode, str] = {
    DiagnosisCode.ACNE: "Mụn trứng cá",
    DiagnosisCode.ACTINIC_KERATOSIS: "Dày sừng quang hoá",
    DiagnosisCode.BENIGN_TUMORS: "U lành tính",
    DiagnosisCode.BULLOUS: "Bệnh da bọng nước",
    DiagnosisCode.CANDIDIASIS: "Nhiễm nấm Candida",
    DiagnosisCode.DRUG_ERUPTION: "Phát ban do thuốc",
    DiagnosisCode.ECZEMA: "Chàm (eczema)",
    DiagnosisCode.INFESTATIONS_BITES: "Ký sinh trùng / côn trùng cắn",
    DiagnosisCode.LICHEN: "Lichen",
    DiagnosisCode.LUPUS: "Lupus",
    DiagnosisCode.MOLES: "Nốt ruồi",
    DiagnosisCode.PSORIASIS: "Vảy nến",
    DiagnosisCode.ROSACEA: "Trứng cá đỏ (rosacea)",
    DiagnosisCode.SEBORRH_KERATOSES: "Dày sừng tiết bã",
    DiagnosisCode.SKIN_CANCER: "Ung thư da",
    DiagnosisCode.SUN_DAMAGE: "Tổn thương do ánh nắng",
    DiagnosisCode.TINEA: "Nấm da (tinea)",
    DiagnosisCode.UNKNOWN_NORMAL: "Da bình thường / không xác định",
    DiagnosisCode.VASCULAR_TUMORS: "U mạch máu",
    DiagnosisCode.VASCULITIS: "Viêm mạch",
    DiagnosisCode.VITILIGO: "Bạch biến",
    DiagnosisCode.WARTS: "Mụn cóc",
    DiagnosisCode.OTHER: "Khác (ngoài danh mục)",
}


class ProvenanceKind(str, Enum):
    CHAT = "chat"  # AI trích từ tin nhắn của bệnh nhân
    DOCTOR = "doctor"  # bác sĩ ghi / xác nhận lúc chốt


class EpisodeStatus(str, Enum):
    OPEN = "open"  # đang thu thập qua chat, giả thuyết còn cập nhật
    IN_EXAM = "in_exam"  # bác sĩ đã bắt đầu khám: khoá giả thuyết, fact vẫn sửa được
    CLOSED = "closed"  # đã chốt kết luận
    EXPIRED = "expired"  # quá hạn không cập nhật, chưa từng khám


class HypothesisConfidence(str, Enum):
    """Giữ đúng 3 mức node `reflect` của graph v2 trả, không đổi sang số."""

    HIGH = "cao"
    MEDIUM = "vừa"
    LOW = "thấp"


class AppointmentStatus(str, Enum):
    REQUESTED = "requested"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"  # bác sĩ đã bấm "Bắt đầu khám"
    DONE = "done"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class EncounterStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


# Fact dài hạn sống theo hồ sơ; các loại còn lại sống theo đợt bệnh
LONG_TERM_FACT_TYPES: frozenset[ClinicalFactType] = frozenset(
    {ClinicalFactType.ALLERGY, ClinicalFactType.HISTORY, ClinicalFactType.MEDICATION}
)
