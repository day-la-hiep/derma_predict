package vn.derma.clinical.client;

import lombok.extern.slf4j.Slf4j;
import java.util.Optional;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import vn.derma.clinical.common.Http11;
import vn.derma.clinical.common.ApiResponse;
import vn.derma.clinical.common.AppException;
import vn.derma.clinical.config.DermaProperties;

/** Xác định hồ sơ bệnh nhân thuộc về ai: bảng `patient_profiles` nằm ở identity. */
@Component
@Slf4j
public class IdentityClient {

    public record ProfileRef(String id, String userId, String fullName) {
    }

    public record UserRef(String id, String fullName, String role) {
    }

    public record ProfileDetail(String id, String userId, String fullName, String dob, String gender, String relationship, String phone) {
    }


    private final RestClient http;

    public IdentityClient(DermaProperties properties, RestClient.Builder builder) {
        this.http = Http11.apply(builder).baseUrl(properties.identityUrl()).defaultHeader("X-Internal-Key", properties.internalApiKey()).build();
    }

    /** Mọi hồ sơ của tài khoản; identity lỗi thì ném 502 (không biết hồ sơ thì không liệt kê được lịch hẹn). */
    public java.util.List<ProfileDetail> listProfilesOfUser(String userId) {
        try {
            ApiResponse<java.util.List<ProfileDetail>> body = http.get().uri("/internal/patient-profiles/by-user?user_id={id}", userId)
                    .retrieve().body(new ParameterizedTypeReference<ApiResponse<java.util.List<ProfileDetail>>>() {
                    });
            return body == null || body.data() == null ? java.util.List.of() : body.data();
        } catch (RestClientException e) {
            log.error("Không lấy được hồ sơ của tài khoản {} từ identity", userId, e);
            throw AppException.badGateway("Không lấy được hồ sơ bệnh nhân (dịch vụ tài khoản không phản hồi).");
        }
    }

    public Optional<UserRef> getUser(String userId) {
        try {
            ApiResponse<UserRef> body = http.get().uri("/internal/users/{id}", userId)
                    .retrieve().onStatus(status -> status.value() == 404, (req, res) -> {
                    }).body(new ParameterizedTypeReference<ApiResponse<UserRef>>() {
                    });
            return body == null ? Optional.empty() : Optional.ofNullable(body.data());
        } catch (RestClientException e) {
            log.error("Không lấy được tài khoản {} từ identity", userId, e);
            throw AppException.badGateway("Không lấy được thông tin tài khoản (dịch vụ tài khoản không phản hồi).");
        }
    }

    /** Hồ sơ nhiều bệnh nhân một lần; identity lỗi thì trả rỗng để danh sách ca vẫn hiện (thiếu thông tin chi tiết), có log. */
    public java.util.Map<String, ProfileDetail> getProfiles(java.util.Collection<String> profileIds) {
        if (profileIds.isEmpty()) {
            return java.util.Map.of();
        }
        try {
            ApiResponse<java.util.List<ProfileDetail>> body = http.get().uri("/internal/patient-profiles?ids={ids}", String.join(",", profileIds))
                    .retrieve().body(new ParameterizedTypeReference<ApiResponse<java.util.List<ProfileDetail>>>() {
                    });
            java.util.Map<String, ProfileDetail> out = new java.util.HashMap<>();
            if (body != null && body.data() != null) {
                body.data().forEach(p -> out.put(p.id(), p));
            }
            return out;
        } catch (RestClientException e) {
            log.warn("Không lấy được hồ sơ bệnh nhân {} từ identity", profileIds, e);
            return java.util.Map.of();
        }
    }

    /** Hồ sơ `profileId` của `userId`, hoặc hồ sơ đầu tiên của tài khoản khi `profileId` null; rỗng nếu không có/không phải của tài khoản. */
    public Optional<ProfileRef> resolveProfile(String userId, String profileId) {
        try {
            ApiResponse<ProfileRef> body = http.get()
                    .uri(uriBuilder -> {
                        var b = uriBuilder.path("/internal/patient-profiles/resolve").queryParam("user_id", userId);
                        return (profileId == null ? b : b.queryParam("profile_id", profileId)).build();
                    })
                    .retrieve()
                    .onStatus(status -> status.value() == 404, (req, res) -> {
                    })
                    .body(new ParameterizedTypeReference<ApiResponse<ProfileRef>>() {
                    });
            return body == null ? Optional.empty() : Optional.ofNullable(body.data());
        } catch (RestClientException e) {
            log.error("Không xác định được hồ sơ {} của tài khoản {} qua identity", profileId, userId, e);
            throw AppException.badGateway("Không kiểm tra được hồ sơ bệnh nhân (dịch vụ tài khoản không phản hồi).");
        }
    }
}
