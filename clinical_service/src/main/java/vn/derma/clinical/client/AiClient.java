package vn.derma.clinical.client;

import java.net.http.HttpClient;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import lombok.extern.slf4j.Slf4j;
import vn.derma.clinical.common.ApiResponse;
import vn.derma.clinical.common.AppException;
import vn.derma.clinical.config.DermaProperties;

/** Gọi ai: chuyển mô tả của bác sĩ thành dữ kiện lúc chốt kết luận. Lỗi thì ném 502 vì không được chốt thiếu dữ kiện. */
@Component
@Slf4j
public class AiClient {

    public record DescribedFact(String factType, String label, String detail) {
    }

    private record Data(List<DescribedFact> facts) {
    }

    private final RestClient http;

    public AiClient(DermaProperties properties, RestClient.Builder builder) {
        // cùng lý do với Http11 (ép HTTP/1.1) cộng thêm hạn đọc dài hơn mặc định vì có một lời gọi LLM
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).build());
        factory.setReadTimeout(Duration.ofSeconds(60));
        this.http = builder.requestFactory(factory).baseUrl(properties.aiUrl()).defaultHeader("X-Internal-Key", properties.internalApiKey()).build();
    }

    /** `known` là các dữ kiện đã giữ; ai chỉ trả dữ kiện mới hoặc đổi giá trị so với chúng. */
    public List<DescribedFact> extractFactsFromDescription(String description, String bodySite, List<DescribedFact> known) {
        try {
            ApiResponse<Data> body = http.post().uri("/internal/extract-facts-from-description")
                    .body(Map.of("description", description, "body_site", bodySite, "known_facts", known)).retrieve()
                    .body(new ParameterizedTypeReference<ApiResponse<Data>>() {
                    });
            return body == null || body.data() == null || body.data().facts() == null ? List.of() : body.data().facts();
        } catch (RestClientException e) {
            log.error("Không chuyển được mô tả của bác sĩ thành dữ kiện (ai lỗi hoặc quá hạn)", e);
            throw AppException.badGateway("Chưa chuyển được mô tả thành dữ kiện, vui lòng thử lại.");
        }
    }
}
