from app.common.constant import BodySite, DiagnosisCode

# mô tả cho LLM; phần trong ngoặc chỉ để giải thích, giá trị phải là mã đứng trước
BODY_SITE_CHOICES = (
    "dau_mat (mặt, má, trán, mũi, cằm, môi, tai, mí mắt) | da_dau_toc (da đầu, tóc) | co | than_truoc (ngực, bụng) | "
    "lung | tay (vai, cánh tay, khuỷu, cẳng tay, cổ tay, nách) | ban_tay (lòng / mu bàn tay, ngón tay) | "
    "chan (mông, háng, đùi, đầu gối, cẳng chân, mắt cá) | ban_chan (lòng / mu bàn chân, ngón chân, kẽ chân) | "
    "sinh_duc | mong (móng tay, móng chân) | nhieu_vung (cùng một bệnh ở từ 2 vùng KHÁC NHAU trong danh sách này)"
)

# shortcut: bảng tên tay cho 22 lớp của CNN (tiếng Anh + tiếng Việt thường gặp), lớp mới thì thêm vào đây; tên ngoài bảng chỉ so khớp theo chuỗi.
ALIASES: dict[str, tuple[str, ...]] = {
    "Acne": ("acne", "mụn trứng cá"),
    "Actinic_Keratosis": ("actinic keratosis", "dày sừng quang hoá", "dày sừng quang hóa", "dày sừng ánh nắng"),
    "Benign_tumors": ("benign", "u lành", "u nang", "lipoma"),
    "Bullous": ("bullous", "pemphig", "bóng nước", "bọng nước"),
    "Candidiasis": ("candida", "nấm men"),
    "DrugEruption": ("drug eruption", "phát ban do thuốc", "dị ứng thuốc", "ban đỏ do thuốc"),
    "Eczema": ("eczema", "atopic", "viêm da cơ địa", "chàm", "contact dermatitis", "viêm da tiếp xúc"),
    "Infestations_Bites": ("scabies", "ghẻ", "côn trùng", "bite", "chấy", "rận"),
    "Lichen": ("lichen", "liken"),
    "Lupus": ("lupus",),
    "Moles": ("nốt ruồi", "mole", "nevus"),
    "Psoriasis": ("psoriasis", "vảy nến"),
    "Rosacea": ("rosacea", "trứng cá đỏ"),
    "Seborrh_Keratoses": ("seborrheic keratosis", "dày sừng tiết bã", "dày sừng bã"),
    "SkinCancer": ("ung thư da", "carcinoma", "melanoma", "skin cancer"),
    "Sun_Sunlight_Damage": ("sun damage", "tổn thương do nắng", "cháy nắng", "sunlight"),
    "Tinea": ("tinea", "nấm da", "hắc lào", "lang ben"),
    "Vascular_Tumors": ("hemangioma", "u mạch", "u máu"),
    "Vasculitis": ("vasculitis", "viêm mạch"),
    "Vitiligo": ("vitiligo", "bạch biến"),
    "Warts": ("wart", "mụn cóc"),
}


def canon(name: str) -> str:
    """Tên bệnh về mã lớp CNN nếu khớp bảng tên (Việt hoặc Anh), không thì chuỗi chữ thường."""
    low = name.lower().replace("_", " ")
    for cls, aliases in ALIASES.items():
        if cls.lower().replace("_", " ") in low or any(a in low for a in aliases):
            return cls
    return low.strip()


def normalize_code(code: str, disease: str) -> DiagnosisCode:
    """Mã LLM ghi nếu hợp lệ; không thì suy từ tên bệnh qua bảng tên; không khớp lớp nào thì OTHER."""
    raw = (code or "").strip()
    for c in DiagnosisCode:
        if raw.lower() == c.value.lower():
            return c
    guessed = canon(disease or raw)
    return DiagnosisCode(guessed) if guessed in DiagnosisCode._value2member_map_ else DiagnosisCode.OTHER


def normalize_body_site(value: str) -> BodySite | None:
    raw = (value or "").strip().lower()
    return BodySite(raw) if raw in BodySite._value2member_map_ else None
