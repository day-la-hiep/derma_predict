package vn.derma.consultation.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public final class ConversationDtos {

    private ConversationDtos() {
    }

    /** `userId` không còn trong body: chủ hội thoại luôn là tài khoản trong JWT. */
    public record CreateConversationInput(@NotNull String content, String patientProfileId, String title, String model, String imageModel) {
    }

    public record UpdateConversationModelInput(@NotBlank String model) {
    }

    public record UpdateConversationImageModelInput(@NotBlank String imageModel) {
    }

    public record ConversationOutput(String id, String patientProfileId, String title, String model, String imageModel, String createdAt, String updatedAt) {
    }

    public record ModelOption(String id) {
    }
}
