package vn.derma.clinical.dto;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

/**
 * DTO của lịch hẹn, đợt bệnh và lần khám; JSON snake_case giữ nguyên như `core/` để FE không đổi.
 */
public final class AppointmentDtos {

  public static final String AI_DISCLAIMER =
      "Gợi ý của AI để hỗ trợ bác sĩ, không phải chẩn đoán y khoa.";

  private AppointmentDtos() {
  }

  public record BookAppointmentInput(@NotBlank String patientProfileId, @NotBlank String episodeId,
                                     @NotNull Instant scheduledAt, @Size(max = 500) String reason) {
  }

  public record CancelAppointmentInput(@NotBlank @Size(max = 500) String reason) {
  }

  public record ChangeEpisodeInput(@NotBlank String episodeId) {
  }

  public record AppointmentOutput(String id, String patientProfileId, String episodeId,
                                  String bodySite, String bodySiteLabel, String doctorId,
                                  String doctorName, String scheduledAt, String status,
                                  String reason, String cancelReason, String createdAt,
                                  String encounterId) {
  }

  public record PatientEpisodeOutput(String id, String bodySite, String bodySiteLabel,
                                     String status, String updatedAt, List<String> facts,
                                     boolean bookable, String notBookableReason,
                                     AppointmentOutput appointment) {
  }

  /** `ref` (document_id, chunk_id, page_start, page_end) chỉ có ở bằng chứng sách từ khi có truy vết; ca cũ là null */
  public record HypothesisEvidenceOutput(String source, String text, Map<String, Object> ref) {
  }

  public record HypothesisOutput(int rank, String diagnosisCode, String diagnosisLabel,
                                 String disease, String confidence,
                                 List<HypothesisEvidenceOutput> evidence, List<String> missing) {
  }

  public record FileDto(String fileName, String storageKey, String contentType, Long size,
                        String createdAt, String url) {
  }

  public record LabelScoreOutput(String label, String labelName, double score) {
  }

  /**
   * `fileId` giữ tên trường cũ cho FE; giá trị là khoá lưu trữ của ảnh.
   */
  public record ImagePredictionOutput(String fileId, FileDto file, List<LabelScoreOutput> topK) {
  }

  public record SourceMessageOutput(String id, String sender, String content, String createdAt) {
  }

  public record ClinicalFactOutput(String id, String templateLabel, String factType, String detail,
                                   String verifiedAt, String createdAt, String updatedAt,
                                   List<String> sourceMessageIds,
                                   List<SourceMessageOutput> sourceMessages) {
  }

  public record PatientProfileDto(String id, String fullName, String dob, String gender,
                                  String relationship, String phone, String allergies,
                                  String medicalHistory) {
  }

  public record DoctorEpisodeOutput(String id, String bodySite, String bodySiteLabel, String status,
                                    String summary, String summaryAt, String urgency,
                                    List<String> redFlags, List<HypothesisOutput> hypotheses,
                                    boolean hypothesesLocked, List<ClinicalFactOutput> facts,
                                    List<ImagePredictionOutput> imagePredictions, String updatedAt,
                                    String disclaimer) {
  }

  public record DoctorAppointmentItemOutput(String id, String patientProfileId, String episodeId,
                                            String bodySite, String bodySiteLabel, String doctorId,
                                            String doctorName, String scheduledAt, String status,
                                            String reason, String cancelReason, String createdAt,
                                            String encounterId,
                                            PatientProfileDto patient, String topHypothesis) {
  }

  public record DoctorAppointmentDetailOutput(String id, String patientProfileId, String episodeId,
                                              String bodySite, String bodySiteLabel,
                                              String doctorId,
                                              String doctorName, String scheduledAt, String status,
                                              String reason, String cancelReason, String createdAt,
                                              String encounterId,
                                              PatientProfileDto patient, String topHypothesis,
                                              DoctorEpisodeOutput episode,
                                              List<ClinicalFactOutput> longTermFacts,
                                              List<PatientEpisodeOutput> otherEpisodes) {
  }
}
