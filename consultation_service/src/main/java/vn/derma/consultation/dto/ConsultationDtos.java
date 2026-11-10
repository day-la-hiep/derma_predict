package vn.derma.consultation.dto;

import java.util.List;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public final class ConsultationDtos {

    private ConsultationDtos() {
    }

    public record RequestConsultationInput(@NotBlank @Size(max = 200) String reason) {
    }

    public record DoctorReplyInput(@NotBlank String content) {
    }

    /** Báo cáo tiền tư vấn do ai gửi về: `status` = `ready` hoặc `failed` (cả hai đều lưu `reportSummary`). */
    public record SessionReportInput(@NotBlank String reportSummary, String status) {
    }

    public record PatientProfileDto(String id, String fullName, String dob, String gender, String relationship, String phone,
            String allergies, String medicalHistory) {
    }

    public record PreConsultationReportOutput(String id, String summary, String createdAt) {
    }

    /** `clinicalFacts` luôn rỗng cho tới khi clinical có endpoint fact kèm tin nguồn (todo 5.3). */
    public record ConsultationSessionOutput(String id, String conversationId, String conversationTitle, PatientProfileDto patient,
            String doctorId, String status, String reason, String requestedAt, String startedAt, String resolvedAt,
            PreConsultationReportOutput report, List<Object> clinicalFacts) {
    }

    public record LatestReportOutput(String summary) {
    }
}
