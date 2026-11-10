package vn.derma.consultation.controller;

import lombok.AllArgsConstructor;
import java.util.List;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import jakarta.validation.Valid;
import vn.derma.consultation.common.ApiResponse;
import vn.derma.consultation.common.AppException;
import vn.derma.consultation.dto.ConsultationDtos.LatestReportOutput;
import vn.derma.consultation.dto.ConsultationDtos.SessionReportInput;
import vn.derma.consultation.dto.MessageDtos.ConversationInfo;
import vn.derma.consultation.dto.MessageDtos.HistoryItem;
import vn.derma.consultation.dto.MessageDtos.MessageInfo;
import vn.derma.consultation.dto.MessageDtos.TurnResultInput;
import vn.derma.consultation.mapper.ConsultationMapper;
import vn.derma.consultation.repository.ConversationRepository;
import vn.derma.consultation.service.ConsultationService;
import vn.derma.consultation.service.MessageService;

/** Chỉ cho service khác (interceptor kiểm `X-Internal-Key`), không qua gateway. Danh sách ở services/contracts/README.md mục 3. */
@RestController
@RequestMapping("/internal")
@AllArgsConstructor
public class InternalController {

    private final ConversationRepository conversations;
    private final MessageService messages;
    private final ConsultationService consultations;
    private final ConsultationMapper mapper;

    @GetMapping("/conversations/{conversationId}")
    ApiResponse<ConversationInfo> getConversation(@PathVariable String conversationId) {
        return conversations.findById(conversationId)
                .map(c -> new ApiResponse<>(mapper.toConversationInfo(c)))
                .orElseThrow(() -> AppException.notFound("hội thoại"));
    }

    /** clinical lấy nội dung tin để chép nguồn của fact và snapshot báo cáo kết luận. */
    @GetMapping("/messages")
    ApiResponse<List<MessageInfo>> getMessages(@RequestParam("ids") String ids) {
        return new ApiResponse<>(messages.describe(java.util.Arrays.stream(ids.split(",")).map(String::trim).filter(x -> !x.isEmpty()).toList()));
    }

    @GetMapping("/conversations/{conversationId}/history")
    ApiResponse<List<HistoryItem>> getHistory(@PathVariable String conversationId) {
        return new ApiResponse<>(messages.history(conversationId));
    }

    @PostMapping("/turns/{messageId}/result")
    ApiResponse<Void> postTurnResult(@PathVariable String messageId, @Valid @RequestBody TurnResultInput body) {
        messages.applyTurnResult(messageId, body);
        return new ApiResponse<>(null);
    }

    /** identity hỏi trước khi xoá hồ sơ: hồ sơ đã có hội thoại chưa. */
    @GetMapping("/patients/{profileId}/has-data")
    ApiResponse<Map<String, Boolean>> hasData(@PathVariable String profileId) {
        return new ApiResponse<>(Map.of("has_data", conversations.existsByPatientProfileId(profileId)));
    }

    /** ai ghi báo cáo tiền tư vấn của phiên (`status` = ready | failed; cả hai đều lưu văn bản báo cáo). */
    @PostMapping("/sessions/{sessionId}/report")
    ApiResponse<Void> saveReport(@PathVariable String sessionId, @Valid @RequestBody SessionReportInput body) {
        consultations.saveReport(sessionId, body.reportSummary());
        return new ApiResponse<>(null);
    }

    /** ai kéo báo cáo tiền tư vấn gần nhất của hồ sơ, trừ phiên đang sinh báo cáo. */
    @GetMapping("/patients/{profileId}/latest-report")
    ApiResponse<LatestReportOutput> latestReport(@PathVariable String profileId, @RequestParam("exclude_session_id") String excludeSessionId) {
        return new ApiResponse<>(new LatestReportOutput(consultations.latestReportSummary(profileId, excludeSessionId).orElse(null)));
    }

    /** clinical đọc phiên (hồ sơ, bác sĩ, trạng thái) trước khi cho chốt báo cáo. */
    @GetMapping("/sessions/{sessionId}")
    ApiResponse<Map<String, String>> getSession(@PathVariable String sessionId) {
        return new ApiResponse<>(consultations.getSessionInfo(sessionId));
    }

    /** clinical báo đã chốt báo cáo kết luận của phiên: đóng phiên và phát mốc kết thúc. */
    @PostMapping("/sessions/{sessionId}/finalized")
    ApiResponse<Void> markFinalized(@PathVariable String sessionId, @RequestBody Map<String, String> body) {
        String doctorId = body.get("doctor_id");
        if (doctorId == null || doctorId.isBlank()) {
            throw AppException.badRequest("Thiếu doctor_id.");
        }
        consultations.markFinalized(sessionId, doctorId);
        return new ApiResponse<>(null);
    }
}
