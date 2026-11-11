package vn.derma.clinical.client;

import lombok.extern.slf4j.Slf4j;
import java.time.Instant;
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import vn.derma.clinical.common.ApiResponse;
import vn.derma.clinical.common.Http11;
import vn.derma.clinical.config.DermaProperties;

/** Gọi consultation: nội dung tin (nguồn của fact) và kênh chat theo dõi sau khám. */
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

    /** Mở kênh theo dõi khi bắt đầu khám; lỗi chỉ ghi log vì khám vẫn tiến hành, kênh được tạo bù khi chốt kết luận. */
    public void openFollowupChannel(String encounterId, String patientProfileId, String doctorId) {
        try {
            createChannel(encounterId, patientProfileId, doctorId);
        } catch (RestClientException e) {
            log.warn("Không mở được kênh theo dõi cho lần khám {}", encounterId, e);
        }
    }

    /** Sau khi chốt: tạo kênh nếu thiếu rồi đặt hạn; lỗi chỉ ghi log vì báo cáo đã lưu, không rollback. */
    public void openFollowupUntil(String encounterId, String patientProfileId, String doctorId, Instant until) {
        try {
            createChannel(encounterId, patientProfileId, doctorId);
            http.put().uri("/internal/encounters/{id}/followup-channel/until", encounterId).body(Map.of("followup_until", until.toString())).retrieve().toBodilessEntity();
        } catch (RestClientException e) {
            log.error("Không đặt được hạn kênh theo dõi cho lần khám {}", encounterId, e);
        }
    }

    private void createChannel(String encounterId, String patientProfileId, String doctorId) {
        http.post().uri("/internal/encounters/{id}/followup-channel", encounterId)
                .body(Map.of("patient_profile_id", patientProfileId, "doctor_id", doctorId)).retrieve().toBodilessEntity();
    }
}
