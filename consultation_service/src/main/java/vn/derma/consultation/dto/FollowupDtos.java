package vn.derma.consultation.dto;

import java.time.Instant;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public final class FollowupDtos {

    private FollowupDtos() {
    }

    /** `status`: open | read_only. Bốn trường cuối chỉ có ở danh sách của bác sĩ. */
    public record FollowupChannelOutput(String conversationId, String encounterId, String status, String followupUntil, String doctorId,
            String doctorName, String patientProfileId, String patientName, String lastMessageAt, String preview) {
    }

    public record CreateChannelInput(@NotBlank String patientProfileId, @NotBlank String doctorId) {
    }

    public record ChannelCreated(String conversationId) {
    }

    public record SetUntilInput(@NotNull Instant followupUntil) {
    }
}
