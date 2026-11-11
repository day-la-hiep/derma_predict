package vn.derma.consultation.controller;

import lombok.AllArgsConstructor;
import java.util.List;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import jakarta.validation.Valid;
import vn.derma.consultation.common.ApiResponse;
import vn.derma.consultation.common.AppException;
import vn.derma.consultation.dto.FollowupDtos.ChannelCreated;
import vn.derma.consultation.dto.FollowupDtos.CreateChannelInput;
import vn.derma.consultation.dto.FollowupDtos.SetUntilInput;
import vn.derma.consultation.dto.MessageDtos.ConversationInfo;
import vn.derma.consultation.dto.MessageDtos.HistoryItem;
import vn.derma.consultation.dto.MessageDtos.MessageInfo;
import vn.derma.consultation.dto.MessageDtos.TurnResultInput;
import vn.derma.consultation.mapper.ConsultationMapper;
import vn.derma.consultation.repository.ConversationRepository;
import vn.derma.consultation.service.FollowupService;
import vn.derma.consultation.service.MessageService;

/** Chỉ cho service khác (interceptor kiểm `X-Internal-Key`), không qua gateway. Danh sách ở services/contracts/README.md mục 3. */
@RestController
@RequestMapping("/internal")
@AllArgsConstructor
public class InternalController {

    private final ConversationRepository conversations;
    private final MessageService messages;
    private final FollowupService followups;
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

    /** clinical mở kênh theo dõi khi bắt đầu khám; idempotent theo lần khám. */
    @PostMapping("/encounters/{encounterId}/followup-channel")
    ApiResponse<ChannelCreated> createFollowupChannel(@PathVariable String encounterId, @Valid @RequestBody CreateChannelInput body) {
        return new ApiResponse<>(new ChannelCreated(followups.createChannel(encounterId, body.patientProfileId(), body.doctorId())));
    }

    /** clinical đặt hạn kênh khi chốt kết luận. */
    @PutMapping("/encounters/{encounterId}/followup-channel/until")
    ApiResponse<Void> setFollowupUntil(@PathVariable String encounterId, @Valid @RequestBody SetUntilInput body) {
        followups.setUntil(encounterId, body.followupUntil());
        return new ApiResponse<>(null);
    }
}
