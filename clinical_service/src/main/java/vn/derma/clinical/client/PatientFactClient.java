package vn.derma.clinical.client;

import java.util.Collection;
import java.util.List;
import java.util.Map;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import lombok.extern.slf4j.Slf4j;
import vn.derma.clinical.common.ApiResponse;
import vn.derma.clinical.common.AppException;
import vn.derma.clinical.common.Http11;
import vn.derma.clinical.config.DermaProperties;

/** Gọi knowledge để đọc và ghi fact trong graph theo dõi của bệnh nhân. Không đọc được thì ném 502: không được hiển thị hồ sơ thiếu dị ứng/tiền sử một cách âm thầm. */
@Component
@Slf4j
public class PatientFactClient {

    public record Lesion(String id, String siteText, String scope) {
    }

    public record GraphFact(String id, String factType, String lesionId, Integer category, String relation, String label, String kgName, String detail,
            String objectType, String kgNodeId, Boolean present, String status, String name, String kind, String effect, String of, String onsetText,
            String onsetAt, String observedAt, String lastConfirmedAt, boolean stale, String sourceMessageId, String linkMethod) {
    }

    public record GraphFacts(List<Lesion> lesions, List<GraphFact> facts) {
    }

    private final RestClient http;

    public PatientFactClient(DermaProperties properties, RestClient.Builder builder) {
        this.http = Http11.apply(builder).baseUrl(properties.knowledgeUrl()).defaultHeader("X-Internal-Key", properties.internalApiKey()).build();
    }

    public GraphFacts getFacts(String profileId) {
        try {
            ApiResponse<GraphFacts> body = http.get().uri("/internal/patient-facts/{id}", profileId).retrieve().body(new ParameterizedTypeReference<ApiResponse<GraphFacts>>() {
            });
            return body == null || body.data() == null ? new GraphFacts(List.of(), List.of()) : body.data();
        } catch (RestClientException e) {
            throw unavailable("đọc dữ kiện của hồ sơ " + profileId, e);
        }
    }

    public Map<String, List<GraphFact>> getLongTerm(Collection<String> profileIds) {
        try {
            ApiResponse<Map<String, List<GraphFact>>> body = http.get().uri("/internal/patient-facts/long-term?profile_ids={ids}", String.join(",", profileIds)).retrieve()
                    .body(new ParameterizedTypeReference<ApiResponse<Map<String, List<GraphFact>>>>() {
                    });
            return body == null || body.data() == null ? Map.of() : body.data();
        } catch (RestClientException e) {
            throw unavailable("đọc dị ứng/tiền sử/thuốc của " + profileIds.size() + " hồ sơ", e);
        }
    }

    private static AppException unavailable(String action, RestClientException e) {
        log.error("Không {} được từ knowledge", action, e);
        return AppException.badGateway("Chưa kết nối được hệ thống tri thức để " + action + ", vui lòng thử lại.");
    }
}
