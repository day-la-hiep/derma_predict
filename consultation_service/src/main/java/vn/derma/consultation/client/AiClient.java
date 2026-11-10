package vn.derma.consultation.client;

import java.util.List;
import java.util.Map;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import vn.derma.consultation.common.Http11;
import vn.derma.consultation.config.DermaProperties;

/** Gửi lượt sang service ai (`POST /internal/turns`, 202) và dừng lượt; lỗi mạng ném lên để người gọi xử lý. */
@Component
public class AiClient {

    public record AttachmentRef(String fileName, String contentType, String storageKey) {
    }

    /** Khớp `TurnRequest` của ai; chỉ mang id và nội dung, ai tự kéo lịch sử và hồ sơ. */
    public record TurnRequest(String type, String conversationId, String messageId, String userMessageId, String corrId, String content,
            String answer, List<AttachmentRef> attachedFiles, String sessionId, String patientProfileId, String reason) {
    }

    private final RestClient http;

    public AiClient(DermaProperties properties, RestClient.Builder builder) {
        this.http = Http11.apply(builder).baseUrl(properties.aiUrl()).defaultHeader("X-Internal-Key", properties.internalApiKey()).build();
    }

    public void startTurn(TurnRequest request) {
        http.post().uri("/internal/turns").body(request).retrieve().toBodilessEntity();
    }

    /** true nếu ai đang chạy lượt đó và đã huỷ nó. */
    public boolean cancelTurn(String messageId) {
        Map<String, Boolean> body = http.post().uri("/internal/turns/{id}/cancel", messageId).retrieve()
                .body(new ParameterizedTypeReference<Map<String, Boolean>>() {
                });
        return body != null && Boolean.TRUE.equals(body.get("cancelled"));
    }
}
