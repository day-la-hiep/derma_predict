package vn.derma.clinical.client;

import lombok.extern.slf4j.Slf4j;
import java.util.List;
import java.util.Map;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import tools.jackson.databind.JsonNode;
import vn.derma.clinical.common.ApiResponse;
import vn.derma.clinical.common.Http11;
import vn.derma.clinical.config.DermaProperties;

/** Gọi knowledge (Python): nạp ca đã chốt vào Qdrant/đồ thị và lấy gợi ý từ đồ thị tri thức. Gợi ý lỗi thì người gọi tự bỏ qua. */
@Component
@Slf4j
public class KnowledgeClient {

    public record HistoryHints(List<String> conditions, List<String> advice) {
    }

    public record IntentResult(List<Map<String, String>> facts, List<String> notes) {
    }


    private final RestClient http;

    public KnowledgeClient(DermaProperties properties, RestClient.Builder builder) {
        this.http = Http11.apply(builder).baseUrl(properties.knowledgeUrl()).defaultHeader("X-Internal-Key", properties.internalApiKey()).build();
    }

    /** Báo cáo đã lưu rồi nên lỗi chỉ ghi log; ca thiếu trong Qdrant được bù bằng `POST /internal/cases/reindex` của knowledge. */
    public void postCase(Object caseInput, String reportId) {
        try {
            http.post().uri("/internal/cases").body(caseInput).retrieve().toBodilessEntity();
        } catch (RestClientException e) {
            log.warn("Không nạp được báo cáo {} vào knowledge (chạy reindex để bù)", reportId, e);
        }
    }

    public HistoryHints getHistoryHints(String profileId) {
        ApiResponse<HistoryHints> body = http.get().uri("/internal/patients/{id}/history-hints", profileId).retrieve()
                .body(new ParameterizedTypeReference<ApiResponse<HistoryHints>>() {
                });
        return body == null ? new HistoryHints(List.of(), List.of()) : body.data();
    }

    public IntentResult runIntent(String intent, List<String> entities, int limit) {
        ApiResponse<IntentResult> body = http.post().uri("/internal/kg/intent")
                .body(Map.of("intent", intent, "entities", entities, "limit", limit, "translate", false)).retrieve()
                .body(new ParameterizedTypeReference<ApiResponse<IntentResult>>() {
                });
        return body == null ? new IntentResult(List.of(), List.of()) : body.data();
    }

    /** Đồ thị hành trình bệnh nhân, chuyển nguyên cho FE. */
    public JsonNode getJourneyGraph(String profileId) {
        ApiResponse<JsonNode> body = http.get().uri("/internal/patients/{id}/journey-graph", profileId).retrieve()
                .body(new ParameterizedTypeReference<ApiResponse<JsonNode>>() {
                });
        return body == null ? null : body.data();
    }
}
