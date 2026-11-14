package vn.derma.consultation.dto;

import java.util.List;
import java.util.Map;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public final class MessageDtos {

    private MessageDtos() {
    }

    /** Tệp trên wire; `url` là link tạm sinh lại mỗi lần trả tin (link hết hạn nên không lưu). */
    public record FileDto(String fileName, String storageKey, String contentType, Long size, String createdAt, String url) {
    }

    public record AttachedFile(@NotBlank String storageKey) {
    }

    public record SendMessageInput(@NotBlank String clientMessageId, @NotNull String content, String modelId, String imageModelId, List<AttachedFile> attachedFiles) {
    }

    public record AnswerInput(@NotBlank String optionId, @NotBlank String label, Boolean custom) {
    }

    /** `metadata` gộp `message_type`, `attached_files`, `video_call` và phần AI lưu (`reasoning`, `choice`) như `MessageMetadataDto` của core. */
    public record MessageOutput(String id, String conversationId, String sender, String content, String status,
            Map<String, Object> metadata, String createdAt) {
    }

    public record SendMessageResult(MessageOutput userMessage, MessageOutput assistantMessage) {
    }

    /** Kết quả cuối của lượt do ai gửi về (`POST /internal/turns/{messageId}/result`). */
    public record TurnResultInput(@NotBlank String status, String content, Map<String, Object> choice, List<Map<String, Object>> reasoning) {
    }

    public record HistoryItem(String sender, String content, String messageType) {
    }

    /** Tin nhắn cho service khác (clinical chép `quote` làm nguồn của fact và snapshot báo cáo kết luận). */
    public record MessageInfo(String id, String conversationId, String sender, String content, String createdAt, List<FileDto> files) {
    }

    public record ConversationInfo(String userId, String patientProfileId, String model, String imageModel) {
    }
}
