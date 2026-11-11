package vn.derma.identity.client;

import lombok.extern.slf4j.Slf4j;
import java.util.List;
import java.util.Map;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import vn.derma.identity.common.Http11;
import vn.derma.identity.common.ApiResponse;
import vn.derma.identity.common.AppException;
import vn.derma.identity.config.DermaProperties;
import vn.derma.identity.dto.PatientProfileDtos.ProfileFactInput;
import vn.derma.identity.dto.PatientProfileDtos.ProfileFactOutput;

/** Fact dài hạn của hồ sơ nằm ở clinical (services/contracts/README.md mục 3). */
@Component
@Slf4j
public class ClinicalClient {

    private record HasData(boolean hasData) {
    }


    private final RestClient http;

    public ClinicalClient(DermaProperties properties, RestClient.Builder builder) {
        this.http = Http11.apply(builder).baseUrl(properties.clinicalUrl()).defaultHeader("X-Internal-Key", properties.internalApiKey()).build();
    }

    /** Clinical lỗi thì danh sách hồ sơ vẫn trả được, chỉ thiếu fact. */
    public Map<String, List<ProfileFactOutput>> getLongTermFacts(List<String> profileIds) {
        if (profileIds.isEmpty()) {
            return Map.of();
        }
        try {
            ApiResponse<Map<String, List<ProfileFactOutput>>> body = http.get()
                    .uri("/internal/patients/long-term-facts?profile_ids={ids}", String.join(",", profileIds))
                    .retrieve().body(new ParameterizedTypeReference<>() {
                    });
            return body == null || body.data() == null ? Map.of() : body.data();
        } catch (RestClientException e) {
            log.warn("Không lấy được fact dài hạn từ clinical cho {} hồ sơ", profileIds.size(), e);
            return Map.of();
        }
    }

    public List<ProfileFactOutput> replaceLongTermFacts(String profileId, List<ProfileFactInput> facts) {
        try {
            ApiResponse<List<ProfileFactOutput>> body = http.put()
                    .uri("/internal/patients/{id}/long-term-facts", profileId)
                    .body(Map.of("facts", facts))
                    .retrieve().body(new ParameterizedTypeReference<>() {
                    });
            return body == null || body.data() == null ? List.of() : body.data();
        } catch (RestClientException e) {
            log.error("Không ghi được fact dài hạn của hồ sơ {} sang clinical", profileId, e);
            throw AppException.badGateway("Không lưu được dị ứng/tiền sử/thuốc (dịch vụ lâm sàng không phản hồi).");
        }
    }

    public boolean hasPatientData(String profileId) {
        try {
            ApiResponse<HasData> body = http.get().uri("/internal/patients/{id}/has-data", profileId)
                    .retrieve().body(new ParameterizedTypeReference<>() {
                    });
            return body != null && body.data() != null && body.data().hasData();
        } catch (RestClientException e) {
            log.error("Không kiểm tra được dữ liệu lâm sàng của hồ sơ {}", profileId, e);
            throw AppException.badGateway("Không kiểm tra được dữ liệu liên kết của hồ sơ (dịch vụ lâm sàng không phản hồi).");
        }
    }
}
