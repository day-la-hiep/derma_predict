package vn.derma.clinical.client;

import lombok.extern.slf4j.Slf4j;
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import vn.derma.clinical.common.ApiResponse;
import vn.derma.clinical.common.AppException;
import vn.derma.clinical.common.Http11;
import vn.derma.clinical.config.DermaProperties;

/** Gọi consultation: nội dung tin (nguồn của fact) và báo đã chốt báo cáo để đóng phiên tư vấn. */
@Component
@Slf4j
public class ConsultationClient {

    public record FileInfo(String fileName, String storageKey, String contentType, Long size) {
    }

    public record MessageInfo(String id, String conversationId, String sender, String content, String createdAt, List<FileInfo> files) {
    }


    private final RestClient http;

    public ConsultationClient(DermaProperties properties, RestClient.Builder builder) {
        this.http = Http11.apply(builder).baseUrl(properties.consultationUrl()).defaultHeader("X-Internal-Key", properties.internalApiKey()).build();
    }

    public record SessionInfo(String id, String conversationId, String patientProfileId, String doctorId, String doctorName, String status) {
    }

    /** Phiên tư vấn để kiểm quyền chốt báo cáo; không có thì 404, consultation lỗi thì 502 (không chốt khi chưa biết phiên). */
    public SessionInfo getSession(String sessionId) {
        try {
            ApiResponse<SessionInfo> body = http.get().uri("/internal/sessions/{id}", sessionId).retrieve()
                    .body(new ParameterizedTypeReference<ApiResponse<SessionInfo>>() {
                    });
            return body == null ? null : body.data();
        } catch (HttpClientErrorException.NotFound e) {
            throw AppException.notFound("phiên tư vấn " + sessionId);
        } catch (RestClientException e) {
            log.error("Không lấy được phiên tư vấn {} từ consultation", sessionId, e);
            throw AppException.badGateway("Dịch vụ hội thoại không phản hồi, chưa đọc được phiên tư vấn.");
        }
    }

    /** Tin theo id; consultation lỗi thì trả rỗng (fact vẫn lưu, chỉ thiếu nguồn) và ghi log. */
    public Map<String, MessageInfo> getMessages(Collection<String> ids) {
        if (ids.isEmpty()) {
            return Map.of();
        }
        try {
            ApiResponse<List<MessageInfo>> body = http.get().uri("/internal/messages?ids={ids}", String.join(",", ids)).retrieve()
                    .body(new ParameterizedTypeReference<ApiResponse<List<MessageInfo>>>() {
                    });
            Map<String, MessageInfo> out = new HashMap<>();
            if (body != null && body.data() != null) {
                body.data().forEach(m -> out.put(m.id(), m));
            }
            return out;
        } catch (RestClientException e) {
            log.warn("Không lấy được nội dung {} tin từ consultation", ids.size(), e);
            return Map.of();
        }
    }

    /** Chốt báo cáo kết luận xong thì đóng phiên tư vấn; lỗi mạng ném 502 để người gọi biết phiên chưa được đóng. */
    public void markSessionFinalized(String sessionId, String doctorId) {
        try {
            http.post().uri("/internal/sessions/{id}/finalized", sessionId).body(Map.of("doctor_id", doctorId)).retrieve().toBodilessEntity();
        } catch (RestClientException e) {
            log.error("Không báo được consultation đóng phiên {}", sessionId, e);
            throw AppException.badGateway("Đã chốt báo cáo nhưng chưa đóng được phiên tư vấn (dịch vụ hội thoại không phản hồi).");
        }
    }
}
