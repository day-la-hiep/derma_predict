package vn.derma.clinical.dto;

import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import vn.derma.clinical.dto.AppointmentDtos.DoctorEpisodeOutput;
import vn.derma.clinical.dto.AppointmentDtos.FileDto;
import vn.derma.clinical.dto.AppointmentDtos.ImagePredictionOutput;
import vn.derma.clinical.dto.AppointmentDtos.PatientProfileDto;

/** DTO báo cáo kết luận; JSON snake_case giữ như `core/`. Snapshot dùng chung một bộ record cho lưu DB và trả FE (URL ảnh chỉ điền lúc trả). */
public final class FinalizeDtos {

    private FinalizeDtos() {
    }

    public record FactInput(String sourceFactId, @NotBlank String factType, @NotBlank @Size(max = 255) String label, String detail) {
        public FactInput {
            detail = detail == null ? "" : detail;
        }
    }

    /** `fileId` là khoá lưu trữ (storage_key) của ảnh; tên trường giữ nguyên để FE không đổi. */
    public record PatientImageInput(@NotBlank String fileId, String bodySite, String description, String confirmedLabel) {
        public PatientImageInput {
            bodySite = bodySite == null ? "" : bodySite;
            description = description == null ? "" : description;
        }
    }

    /** Một form cho cả chốt ca tư vấn và chốt lần khám; `diagnosisCode` chỉ bắt buộc với lần khám. */
    public record FinalizeInput(@NotBlank String diagnosis, String notes, Boolean isReferenceCase, String reasoning, @NotBlank String urgency,
            List<String> instructions, @Valid List<FactInput> facts, @Valid List<PatientImageInput> images, String diagnosisCode) {
        public FinalizeInput {
            notes = notes == null ? "" : notes;
            isReferenceCase = isReferenceCase != null && isReferenceCase;
            reasoning = reasoning == null ? "" : reasoning;
            instructions = instructions == null ? List.of() : instructions;
            facts = facts == null ? List.of() : facts;
            images = images == null ? List.of() : images;
        }
    }

    // ---- snapshot (bất biến sau khi chốt)

    public record SnapshotMessage(String id, String sender, String content, String createdAt, List<FileDto> files) {
    }

    public record SnapshotProvenance(SnapshotMessage message) {
    }

    public record SnapshotFact(String factType, String label, String detail, String origin, List<SnapshotProvenance> provenances) {
    }

    public record SnapshotProfile(String fullName, String dob, String gender, String relationship, String phone, String allergies, String medicalHistory) {
    }

    public record Assessment(String reasoning, String urgency, List<String> instructions) {
    }

    public record Snapshot(SnapshotProfile patientProfile, Assessment assessment, List<SnapshotFact> clinicalFacts, List<SnapshotFact> removedFacts) {
    }

    // ---- output

    public record PatientImageOutput(String id, FileDto file, String bodySite, String description, String confirmedLabel, String capturedAt) {
    }

    public record FinalizeReportOutput(String id, String diagnosis, String notes, boolean isReferenceCase, String doctorName, String createdAt,
            String consultationSessionId, String conversationId, String encounterId, String diagnosisCode, Snapshot snapshot, List<PatientImageOutput> images) {
    }

    public record FinalizeReportItemOutput(String id, String diagnosis, String notes, boolean isReferenceCase, String doctorName, String createdAt,
            String consultationSessionId, String conversationId, String encounterId, String diagnosisCode, Snapshot snapshot, List<PatientImageOutput> images,
            PatientProfileDto patient) {
    }

    /** Bệnh nhân không thấy cờ nội bộ `is_reference_case` và snapshot. */
    public record PatientFinalizeReportOutput(String id, String diagnosis, String notes, String doctorName, String createdAt) {
    }

    public record DraftFactOutput(String sourceFactId, String factType, String label, String detail, String origin, List<SnapshotProvenance> provenances) {
    }

    /** Gợi ý từ đồ thị tri thức, chỉ để bác sĩ tham khảo, không phải chẩn đoán. */
    public record GraphSuggestionOutput(List<String> previousConditions, List<String> previousAdvice, List<String> candidateDiseases, List<String> redFlags,
            List<String> notes) {
    }

    public record FinalizeDraftOutput(PatientProfileDto patient, List<DraftFactOutput> facts, GraphSuggestionOutput suggestions) {
    }

    public record DiagnosisOptionOutput(String code, String label) {
    }

    public record EncounterDraftOutput(PatientProfileDto patient, List<DraftFactOutput> facts, GraphSuggestionOutput suggestions, String encounterId,
            String appointmentId, DoctorEpisodeOutput episode, List<ImagePredictionOutput> images, List<DiagnosisOptionOutput> diagnosisOptions) {
    }

    // ---- gửi knowledge (`POST /internal/cases`)

    public record CaseImage(String fileId, String storageKey, String fileName, String bodySite, String description, String confirmedLabel) {
    }

    public record CaseInput(String reportId, String patientProfileId, String doctorId, String encounterId, String consultationSessionId, String diagnosis,
            String notes, boolean isReferenceCase, String createdAt, Snapshot snapshot, List<CaseImage> images) {
    }
}
