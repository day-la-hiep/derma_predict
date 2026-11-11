"""Danh mục lâm sàng dùng chung với clinical (Java): đổi một phía phải đổi phía kia cùng lúc (xem services/contracts/README.md)."""
from enum import Enum


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
