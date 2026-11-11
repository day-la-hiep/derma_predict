package vn.derma.clinical.dto;

import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public final class ClinicalDtos {

    private ClinicalDtos() {
    }

    /** Fact dài hạn bệnh nhân tự khai (form hồ sơ ở identity). */
    public record ProfileFactInput(@NotNull @Pattern(regexp = "allergy|history|medication") String factType, @NotBlank @Size(max = 255) String label,
            @Size(max = 300) String detail) {
    }

    public record ReplaceLongTermFactsInput(@Valid List<ProfileFactInput> facts) {
    }

    public record ProfileFactOutput(String id, String factType, String label, String detail, String verifiedAt) {
    }

    /** Kết quả lâm sàng của một lượt do ai gửi; phần tử `facts`/`hypotheses`/`imagePredictions` giữ dạng map như ai tạo ra. */
    public record ApplyTurnInput(@NotBlank String conversationId, String messageId, @NotBlank String patientProfileId,
            List<Map<String, Object>> facts, List<Map<String, Object>> hypotheses, List<Map<String, Object>> imagePredictions) {
    }

    /** Fact hiện trạng cho agent nạp mỗi lượt. */
    public record ContextFact(String label, String factType, String detail, String bodySite) {
    }

    public record PatientContext(List<ContextFact> facts) {
    }

    public record HasData(boolean hasData) {
    }
}
