package vn.derma.clinical.dto;

import java.util.List;
import java.util.Map;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public final class ClinicalDtos {

    private ClinicalDtos() {
    }

    /** Kết quả lâm sàng của một lượt do ai gửi; `facts` (nếu có) bị bỏ qua vì fact ghi vào graph theo dõi; `hypotheses`/`imagePredictions` giữ dạng map như ai tạo ra. */
    public record ApplyTurnInput(@NotBlank String conversationId, String messageId, @NotBlank String patientProfileId,
            List<Map<String, Object>> facts, List<Map<String, Object>> hypotheses, List<Map<String, Object>> imagePredictions) {
    }

    public record HasData(boolean hasData) {
    }
}
