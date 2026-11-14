package vn.derma.clinical.model;

import java.time.Instant;
import java.util.Set;

/** Một dữ kiện lâm sàng hiện hành của bệnh nhân, đọc từ graph theo dõi ở knowledge (không lưu trong DB của clinical). */
public class PatientFact {

    private static final Set<String> LONG_TERM_TYPES = Set.of("history", "medication", "allergy");

    /** Id ổn định của cạnh trong graph; form chốt trỏ tới fact nguồn bằng id này. */
    public String id;
    public String patientProfileId;
    /** symptom | lesion | history | medication | allergy | other. */
    public String factType;
    public String label;
    public String detail = "";
    /** false = người bệnh nói không có ("không ngứa"). */
    public boolean present = true;
    public Integer category;
    public String lesionId;
    public String siteText;
    public String onsetText;
    /** Ngày khởi phát ước lượng (yyyy-MM-dd) do knowledge quy đổi; null khi không suy ra được. */
    public String onsetAt;
    public String kgNodeId;
    /** Tên chuẩn (tiếng Anh) của nút đồ thị đã khớp; rỗng khi chưa khớp. */
    public String kgName;
    public String sourceMessageId;
    /** Chưa được nhắc lại quá hạn: nên hỏi lại người bệnh. */
    public boolean stale;
    public Instant createdAt;
    public Instant updatedAt;
    /** Graph không có xác nhận từng dữ kiện; bác sĩ xác nhận khi chốt (snapshot). */
    public Instant verifiedAt;

    public boolean isLongTerm() {
        return LONG_TERM_TYPES.contains(factType);
    }
}
