package vn.derma.clinical.common;

import java.util.Map;
import java.util.Set;

/**
 * Danh mục lâm sàng dùng chung với ai (`services/ai/app/common/constant.py`): sinh từ `core/app/common/constant.py`,
 * đổi một phía phải đổi phía kia cùng lúc (xem services/contracts/README.md).
 */
public final class ClinicalCodes {

    private ClinicalCodes() {
    }

    public static final Map<String, String> BODY_SITE_LABELS = Map.ofEntries(
            Map.entry("dau_mat", "Đầu, mặt"),
            Map.entry("da_dau_toc", "Da đầu, tóc"),
            Map.entry("co", "Cổ"),
            Map.entry("than_truoc", "Ngực, bụng"),
            Map.entry("lung", "Lưng"),
            Map.entry("tay", "Tay"),
            Map.entry("ban_tay", "Bàn tay"),
            Map.entry("chan", "Chân"),
            Map.entry("ban_chan", "Bàn chân"),
            Map.entry("sinh_duc", "Vùng sinh dục"),
            Map.entry("mong", "Móng"),
            Map.entry("nhieu_vung", "Nhiều vùng"));

    public static final Map<String, String> DIAGNOSIS_CODE_LABELS = Map.ofEntries(
            Map.entry("Acne", "Mụn trứng cá"),
            Map.entry("Actinic_Keratosis", "Dày sừng quang hoá"),
            Map.entry("Benign_tumors", "U lành tính"),
            Map.entry("Bullous", "Bệnh da bọng nước"),
            Map.entry("Candidiasis", "Nhiễm nấm Candida"),
            Map.entry("DrugEruption", "Phát ban do thuốc"),
            Map.entry("Eczema", "Chàm (eczema)"),
            Map.entry("Infestations_Bites", "Ký sinh trùng / côn trùng cắn"),
            Map.entry("Lichen", "Lichen"),
            Map.entry("Lupus", "Lupus"),
            Map.entry("Moles", "Nốt ruồi"),
            Map.entry("Psoriasis", "Vảy nến"),
            Map.entry("Rosacea", "Trứng cá đỏ (rosacea)"),
            Map.entry("Seborrh_Keratoses", "Dày sừng tiết bã"),
            Map.entry("SkinCancer", "Ung thư da"),
            Map.entry("Sun_Sunlight_Damage", "Tổn thương do ánh nắng"),
            Map.entry("Tinea", "Nấm da (tinea)"),
            Map.entry("Unknown_Normal", "Da bình thường / không xác định"),
            Map.entry("Vascular_Tumors", "U mạch máu"),
            Map.entry("Vasculitis", "Viêm mạch"),
            Map.entry("Vitiligo", "Bạch biến"),
            Map.entry("Warts", "Mụn cóc"),
            Map.entry("OTHER", "Khác (ngoài danh mục)"));

    public static final Set<String> FACT_TYPES = Set.of("symptom", "lesion", "history", "medication", "allergy", "other");

    public static final Set<String> LONG_TERM_FACT_TYPES = Set.of("allergy", "history", "medication");

    public static final Set<String> URGENCIES = Set.of("emergency", "few_days", "monitor");

    public static final Set<String> HYPOTHESIS_CONFIDENCES = Set.of("cao", "vừa", "thấp");

    public static final Set<String> FACT_ORIGINS = Set.of("patient_reported", "ai_inferred", "doctor_observed", "doctor_corrected");

}
