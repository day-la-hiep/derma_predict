package vn.derma.consultation.service;

import lombok.AllArgsConstructor;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import vn.derma.consultation.common.AppException;
import vn.derma.consultation.dto.VideoCallDtos.VideoCallOutput;
import vn.derma.consultation.mapper.ConsultationMapper;
import vn.derma.consultation.entity.ConsultationSession;
import vn.derma.consultation.entity.Conversation;
import vn.derma.consultation.entity.Message;
import vn.derma.consultation.entity.VideoCall;
import vn.derma.consultation.repository.ConsultationSessionRepository;
import vn.derma.consultation.repository.ConversationRepository;
import vn.derma.consultation.repository.MessageRepository;
import vn.derma.consultation.repository.VideoCallRepository;

/** Vòng đời cuộc gọi giữa bác sĩ (bên gọi) và chủ hội thoại (bên nhận); signaling WebRTC chuyển qua Pub/Sub riêng của từng tài khoản. */
@Service
@AllArgsConstructor
public class VideoCallService {

    private record Participants(ConsultationSession session, VideoCall call, String doctorId, String patientId) {
    }

    private final VideoCallRepository calls;
    private final ConsultationSessionRepository sessions;
    private final ConversationRepository conversations;
    private final MessageRepository messages;
    private final MessageService messageService;
    private final ConversationEvents events;
    private final PubSubStreams pubSub;
    private final ConsultationMapper mapper;

    @Transactional
    public VideoCallOutput start(String conversationId, String userId, String mode) {
        ConsultationSession session = sessions.findFirstByConversationIdAndStatusNot(conversationId, "resolved")
                .filter(s -> "active".equals(s.status)).orElseThrow(() -> AppException.conflict("Chỉ gọi được khi bác sĩ đang tư vấn trong hội thoại này."));
        String patientId = patientOf(session);
        if (!userId.equals(session.doctorId)) {
            throw AppException.forbidden("Chỉ bác sĩ phụ trách mới được khởi tạo cuộc gọi.");
        }
        if (calls.findFirstByConsultationSessionIdAndStatusNot(session.id, "ended").isPresent()) {
            throw AppException.conflict("Phiên này đang có một cuộc gọi chưa kết thúc.");
        }
        VideoCall call = new VideoCall();
        call.consultationSessionId = session.id;
        calls.save(call);
        VideoCallOutput output = mapper.toVideoCallOutput(call, session);
        notify(session.doctorId, patientId, Map.of("type", "call.ringing", "mode", mode == null ? "audio" : mode, "call", output), null);
        return output;
    }

    @Transactional
    public VideoCallOutput accept(String callId, String userId) {
        Participants p = load(callId, userId);
        if (!userId.equals(p.patientId())) {
            throw AppException.forbidden("Chỉ bên nhận mới bắt máy được.");
        }
        if (!"pending".equals(p.call().status)) {
            throw AppException.conflict("Cuộc gọi không còn ở trạng thái chờ bắt máy.");
        }
        p.call().status = "ongoing";
        p.call().startedAt = Instant.now();
        calls.save(p.call());
        VideoCallOutput output = mapper.toVideoCallOutput(p.call(), p.session());
        postLine(p.call(), p.session(), "Cuộc gọi bắt đầu");
        notify(p.doctorId(), p.patientId(), Map.of("type", "call.accepted", "call", output), null);
        return output;
    }

    @Transactional
    public VideoCallOutput end(String callId, String userId, boolean missed) {
        Participants p = load(callId, userId);
        VideoCall call = p.call();
        if ("ended".equals(call.status)) {
            return mapper.toVideoCallOutput(call, p.session()); // hai bên cùng bấm kết thúc: lần sau không lỗi
        }
        String reason = "ongoing".equals(call.status) ? "ended" : userId.equals(p.patientId()) ? "rejected" : missed ? "missed" : "cancelled";
        Instant startedAt = call.startedAt;
        call.status = "ended";
        call.endedAt = Instant.now();
        calls.save(call);
        VideoCallOutput output = mapper.toVideoCallOutput(call, p.session());
        postLine(call, p.session(), endText(call, reason, startedAt));
        notify(p.doctorId(), p.patientId(), Map.of("type", "call.ended", "reason", reason, "ended_by", userId, "call", output), null);
        return output;
    }

    public void signal(String callId, String userId, String kind, Map<String, Object> payload) {
        Participants p = load(callId, userId);
        if (!"ongoing".equals(p.call().status)) {
            throw AppException.conflict("Cuộc gọi chưa bắt đầu hoặc đã kết thúc.");
        }
        String peer = userId.equals(p.doctorId()) ? p.patientId() : p.doctorId();
        notify(p.doctorId(), p.patientId(), Map.of("type", "call.signal", "call_id", p.call().id, "from", userId, "kind", kind, "payload", payload), peer);
    }

    private Participants load(String callId, String userId) {
        VideoCall call = calls.findById(callId).orElseThrow(() -> AppException.notFound("cuộc gọi"));
        ConsultationSession session = sessions.findById(call.consultationSessionId).orElseThrow(() -> AppException.notFound("cuộc gọi"));
        String patientId = patientOf(session);
        if (!userId.equals(session.doctorId) && !userId.equals(patientId)) {
            throw AppException.forbidden("Bạn không thuộc cuộc gọi này.");
        }
        return new Participants(session, call, session.doctorId, patientId);
    }

    /** Bên nhận là chủ hội thoại; phiên chưa có bác sĩ thì chưa gọi được. */
    private String patientOf(ConsultationSession session) {
        Conversation conversation = conversations.findById(session.conversationId).orElse(null);
        if (session.doctorId == null || conversation == null) {
            throw AppException.conflict("Phiên tư vấn chưa có bác sĩ nhận nên chưa gọi được.");
        }
        return conversation.userId;
    }

    /** Event cuộc gọi đi theo kênh riêng của từng người (không qua stream hội thoại) để nhận được ở mọi trang. */
    private void notify(String doctorId, String patientId, Map<String, Object> event, String only) {
        for (String user : new String[] {doctorId, patientId}) {
            if (only == null || user.equals(only)) {
                pubSub.publish(PubSubStreams.userCallsChannel(user), event);
            }
        }
    }

    private static String endText(VideoCall call, String reason, Instant startedAt) {
        if ("ended".equals(reason) && startedAt != null && call.endedAt != null) {
            long seconds = call.endedAt.getEpochSecond() - startedAt.getEpochSecond();
            return String.format("Cuộc gọi kết thúc · %02d:%02d", seconds / 60, seconds % 60);
        }
        return switch (reason) {
            case "rejected" -> "Bệnh nhân đã từ chối cuộc gọi";
            case "cancelled" -> "Bác sĩ đã huỷ cuộc gọi";
            default -> "Cuộc gọi nhỡ";
        };
    }

    /** Tin hệ thống trong luồng chat; mỗi mốc (bắt đầu, kết thúc) là một tin riêng, không sửa lại sau. */
    private void postLine(VideoCall call, ConsultationSession session, String content) {
        Message line = new Message();
        line.conversationId = session.conversationId;
        line.sender = "doctor";
        line.messageType = "video_call";
        line.videoCallId = call.id;
        line.content = content;
        line.status = "done";
        messages.save(line);
        events.publish(session.conversationId, Map.of("type", "message.created", "message", messageService.toOutput(line, java.util.List.of(), call)));
    }

}
