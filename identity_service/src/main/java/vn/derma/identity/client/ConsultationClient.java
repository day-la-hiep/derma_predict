package vn.derma.identity.client;

import lombok.extern.slf4j.Slf4j;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import vn.derma.identity.common.Http11;
import vn.derma.identity.common.ApiResponse;
import vn.derma.identity.common.AppException;
import vn.derma.identity.config.DermaProperties;

@Component
@Slf4j
public class ConsultationClient {

    private record HasData(boolean hasData) {
    }


    private final RestClient http;

    public ConsultationClient(DermaProperties properties, RestClient.Builder builder) {
        this.http = Http11.apply(builder).baseUrl(properties.consultationUrl()).defaultHeader("X-Internal-Key", properties.internalApiKey()).build();
    }

    /** Hồ sơ đã có hội thoại hay chưa; không xác định được thì từ chối xoá (fail closed). */
    public boolean hasPatientData(String profileId) {
        try {
            ApiResponse<HasData> body = http.get().uri("/internal/patients/{id}/has-data", profileId)
                    .retrieve().body(new ParameterizedTypeReference<>() {
                    });
            return body != null && body.data() != null && body.data().hasData();
        } catch (RestClientException e) {
            log.error("Không kiểm tra được hội thoại của hồ sơ {}", profileId, e);
            throw AppException.badGateway("Không kiểm tra được dữ liệu liên kết của hồ sơ (dịch vụ hội thoại không phản hồi).");
        }
    }
}
