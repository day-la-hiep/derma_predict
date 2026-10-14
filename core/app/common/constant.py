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
