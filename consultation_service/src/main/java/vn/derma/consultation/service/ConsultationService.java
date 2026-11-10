package vn.derma.consultation.service;

import lombok.AllArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import vn.derma.consultation.client.AiClient;
import vn.derma.consultation.client.IdentityClient;
import vn.derma.consultation.common.AppException;
import vn.derma.consultation.common.AuthenticatedUser;
import vn.derma.consultation.dto.ConsultationDtos.ConsultationSessionOutput;
import vn.derma.consultation.dto.ConsultationDtos.PatientProfileDto;
import vn.derma.consultation.dto.ConsultationDtos.PreConsultationReportOutput;
import vn.derma.consultation.dto.MessageDtos.MessageOutput;
import vn.derma.consultation.mapper.ConsultationMapper;
import vn.derma.consultation.entity.ConsultationSession;
import vn.derma.consultation.entity.Conversation;
import vn.derma.consultation.entity.Message;
import vn.derma.consultation.entity.PreConsultationReport;
import vn.derma.consultation.repository.ConsultationSessionRepository;
import vn.derma.consultation.repository.ConversationRepository;
import vn.derma.consultation.repository.MessageRepository;
import vn.derma.consultation.repository.PreConsultationReportRepository;

/** Phiên tư vấn giữa bệnh nhân và bác sĩ: yêu cầu, nhận ca, trả lời, đóng ca, báo cáo tiền tư vấn do ai sinh. */
@Service
@Slf4j
@AllArgsConstructor
public class ConsultationService {

    public record RoomAccess(boolean doctor, Instant until, boolean closed) {
    }


    private final ConsultationSessionRepository sessions;
    private final PreConsultationReportRepository reports;
    private final ConversationRepository conversations;
    private final MessageRepository messages;
    private final MessageService messageService;
    private final IdentityClient identity;
    private final AiClient ai;
    private final ConversationEvents events;
    private final PubSubStreams pubSub;
    private final ConsultationMapper mapper;

    /** Chủ hội thoại xem hết; bác sĩ xem từ đầu tới hết phiên gần nhất của mình (ca đã đóng thì tới tin mốc kết thúc). */
    public RoomAccess roomAccess(String conversationId, AuthenticatedUser user) {
        Conversation conversation = conversations.findById(conversationId).orElseThrow(() -> AppException.notFound("hội thoại"));
        if (conversation.userId.equals(user.id())) {
            return new RoomAccess(false, null, false);
        }
        if ("doctor".equals(user.role())) {
            Optional<ConsultationSession> visible = sessions.findLatestVisibleToDoctor(conversationId, user.id());
            if (visible.isPresent()) {
                ConsultationSession s = visible.get();
                if (!"resolved".equals(s.status)) {
                    return new RoomAccess(true, null, false);
                }
                Instant until = messages.findFirstByConsultationSessionIdAndMessageTypeOrderByCreatedAtAsc(s.id, "consultation_resolved")
                        .map(m -> m.createdAt).orElse(s.resolvedAt);
                return new RoomAccess(true, until, true);
            }
        }
        throw AppException.forbidden("Bạn không có quyền xem hội thoại này.");
    }

    @Transactional
    public ConsultationSessionOutput requestConsultation(String conversationId, String userId, String reason) {
        Conversation conversation = conversations.findById(conversationId).orElseThrow(() -> AppException.notFound("hội thoại"));
        if (!conversation.userId.equals(userId)) {
            throw AppException.forbidden("Bạn chỉ có thể yêu cầu bác sĩ cho hội thoại của chính mình.");
        }
        Optional<ConsultationSession> existing = sessions.findFirstByConversationIdAndStatusNot(conversationId, "resolved");
        if (existing.isPresent()) {
            return toOutput(existing.get());
        }
        ConsultationSession session = new ConsultationSession();
        session.conversationId = conversationId;
        session.reason = reason.trim();
        session.patientName = identity.resolveProfile(userId, conversation.patientProfileId).map(IdentityClient.ProfileRef::fullName).orElse(null);
        sessions.save(session);
        Message marker = postMarker(session, "consultation_requested", "patient", "Bạn đã gửi yêu cầu kết nối bác sĩ");
        requestReport(conversation, session, marker);
        ConsultationSessionOutput output = toOutput(session);
        announce(output);
        return output;
    }

    public List<ConsultationSessionOutput> list(String doctorId, String status) {
        List<ConsultationSession> found = sessions.findVisibleToDoctor(doctorId, status == null || "all".equals(status) ? null : status);
        return toOutputs(found);
    }

    public ConsultationSessionOutput get(String sessionId, String doctorId) {
        return toOutput(getOwned(sessionId, doctorId));
    }

    @Transactional
    public ConsultationSessionOutput accept(String sessionId, String doctorId) {
        ConsultationSession session = getOwned(sessionId, doctorId);
        if ("resolved".equals(session.status)) {
            throw AppException.conflict("Ca tư vấn đã được đóng.");
        }
        if ("pending".equals(session.status)) {
            acceptBy(session, doctorId);
        }
        ConsultationSessionOutput output = toOutput(session);
        announce(output);
        return output;
    }

    @Transactional
    public MessageOutput reply(String sessionId, String doctorId, String content) {
        ConsultationSession session = getOwned(sessionId, doctorId);
        if ("resolved".equals(session.status)) {
            throw AppException.conflict("Ca tư vấn đã đóng, không thể gửi thêm tin nhắn.");
        }
        // gửi tin cũng là nhận ca (UI báo trước điều này ở nút gửi)
        boolean accepted = "pending".equals(session.status);
        if (accepted) {
            acceptBy(session, doctorId);
        }
        Message message = new Message();
        message.conversationId = session.conversationId;
        message.sender = "doctor";
        message.content = content;
        message.status = "done";
        message.metadata = "{\"doctorId\":\"" + doctorId + "\"}";
        messages.save(message);
        MessageOutput output = messageService.toOutput(message);
        events.publish(session.conversationId, Map.of("type", "message.created", "message", output));
        if (accepted) {
            announce(toOutput(session));
        }
        return output;
    }

    @Transactional
    public ConsultationSessionOutput resolve(String sessionId, String doctorId) {
        ConsultationSession session = getOwned(sessionId, doctorId);
        if (!"active".equals(session.status)) {
            throw AppException.conflict("Chỉ đóng được ca đang tư vấn (bác sĩ cần nhận ca trước).");
        }
        session.status = "resolved";
        session.resolvedAt = Instant.now();
        sessions.save(session);
        postMarker(session, "consultation_resolved", "doctor", "Bác sĩ " + doctorName(session) + " đã kết thúc phiên tư vấn");
        ConsultationSessionOutput output = toOutput(session);
        announce(output);
        return output;
    }

    /** ai gửi báo cáo tiền tư vấn: lưu (ghi đè nếu đã có) rồi báo cho bác sĩ và bệnh nhân. */
    @Transactional
    public void saveReport(String sessionId, String summary) {
        ConsultationSession session = sessions.findById(sessionId).orElseThrow(() -> AppException.notFound("phiên tư vấn " + sessionId));
        PreConsultationReport report = reports.findByConsultationSessionId(sessionId).orElseGet(PreConsultationReport::new);
        report.consultationSessionId = sessionId;
        report.summary = summary;
        reports.save(report);
        announce(toOutput(session));
        log.info("Đã lưu báo cáo tiền tư vấn của phiên {}", sessionId);
    }

    public Optional<String> latestReportSummary(String profileId, String excludeSessionId) {
        return reports.findLatestOfProfile(profileId, excludeSessionId).map(r -> r.summary);
    }

    /** clinical hỏi phiên thuộc hồ sơ/bác sĩ nào để kiểm quyền trước khi chốt (`GET /internal/sessions/{id}`). */
    public Map<String, String> getSessionInfo(String sessionId) {
        ConsultationSession session = sessions.findById(sessionId).orElseThrow(() -> AppException.notFound("phiên tư vấn " + sessionId));
        Conversation conversation = conversations.findById(session.conversationId).orElseThrow(() -> AppException.notFound("hội thoại"));
        Map<String, String> out = new HashMap<>();
        out.put("id", session.id);
        out.put("conversation_id", session.conversationId);
        out.put("patient_profile_id", conversation.patientProfileId);
        out.put("doctor_id", session.doctorId);
        out.put("doctor_name", session.doctorName);
        out.put("status", session.status);
        return out;
    }

    /** chốt báo cáo kết luận xong ở clinical: đóng phiên và phát mốc kết thúc (clinical gọi, `POST /internal/sessions/{id}/finalized`). */
    @Transactional
    public void markFinalized(String sessionId, String doctorId) {
        ConsultationSession session = getOwned(sessionId, doctorId);
        if (!"resolved".equals(session.status)) {
            session.status = "resolved";
            session.resolvedAt = Instant.now();
            sessions.save(session);
        }
        postMarker(session, "consultation_resolved", "doctor", "Bác sĩ " + doctorName(session) + " đã kết thúc phiên tư vấn");
        announce(toOutput(session));
    }

    private ConsultationSession getOwned(String sessionId, String doctorId) {
        ConsultationSession session = sessions.findById(sessionId).orElseThrow(() -> AppException.notFound("phiên tư vấn id=" + sessionId));
        if (session.doctorId != null && !session.doctorId.equals(doctorId)) {
            throw AppException.forbidden("Ca tư vấn này đang do bác sĩ khác phụ trách.");
        }
        return session;
    }

    private void acceptBy(ConsultationSession session, String doctorId) {
        session.doctorId = doctorId;
        session.doctorName = identity.getUser(doctorId).map(IdentityClient.UserRef::fullName).orElse("Bác sĩ");
        session.status = "active";
        session.startedAt = Instant.now();
        sessions.save(session);
        postMarker(session, "consultation_accepted", "doctor", "Bác sĩ " + doctorName(session) + " đã tham gia cuộc trò chuyện");
    }

    private String doctorName(ConsultationSession session) {
        return session.doctorName == null ? "Bác sĩ" : session.doctorName;
    }

    /** Tin mốc đầu/cuối phiên: hiện thành đường chia trong luồng chat của cả ba bên. */
    private Message postMarker(ConsultationSession session, String type, String sender, String content) {
        Message marker = new Message();
        marker.conversationId = session.conversationId;
        marker.sender = sender;
        marker.messageType = type;
        marker.consultationSessionId = session.id;
        marker.content = content;
        marker.status = "done";
        messages.save(marker);
        events.publish(session.conversationId, Map.of("type", "message.created", "message", messageService.toOutput(marker)));
        return marker;
    }

    /** Nhờ ai sinh báo cáo tiền tư vấn; ai không nhận được thì phiên vẫn tạo (bác sĩ thấy ca chưa có báo cáo), có log. */
    private void requestReport(Conversation conversation, ConsultationSession session, Message marker) {
        try {
            ai.startTurn(new AiClient.TurnRequest("consultation_report", conversation.id, marker.id, null, null, null, null, null,
                    session.id, conversation.patientProfileId, session.reason));
        } catch (RuntimeException e) {
            log.error("Không gửi được yêu cầu sinh báo cáo tiền tư vấn của phiên {} sang ai", session.id, e);
        }
    }

    private void announce(ConsultationSessionOutput output) {
        events.publish(output.conversationId(), java.util.Map.of("type", "consultation.updated", "session_id", output.id(), "status", output.status(),
                "doctor_id", output.doctorId() == null ? "" : output.doctorId()));
        pubSub.publish(PubSubStreams.DOCTOR_INBOX, Map.of("type", "consultation.updated", "session", output));
    }

    private ConsultationSessionOutput toOutput(ConsultationSession session) {
        return toOutputs(List.of(session)).get(0);
    }

    private List<ConsultationSessionOutput> toOutputs(List<ConsultationSession> found) {
        Map<String, Conversation> conversationById = conversations.findAllById(found.stream().map(s -> s.conversationId).distinct().toList())
                .stream().collect(Collectors.toMap(c -> c.id, c -> c));
        Map<String, PreConsultationReport> reportBySession = reports.findByConsultationSessionIdIn(found.stream().map(s -> s.id).toList())
                .stream().collect(Collectors.toMap(r -> r.consultationSessionId, r -> r));
        Map<String, IdentityClient.ProfileDetail> profiles = identity.getProfiles(
                conversationById.values().stream().map(c -> c.patientProfileId).collect(Collectors.toSet()));
        return found.stream().map(s -> {
            Conversation conversation = conversationById.get(s.conversationId);
            PreConsultationReport report = reportBySession.get(s.id);
            return mapper.toSessionOutput(s, conversation == null ? "Hội thoại da liễu" : conversation.title, patientOf(s, conversation, profiles),
                    report == null ? null : mapper.toReportOutput(report));
        }).toList();
    }

    /** Thông tin bệnh nhân lấy từ identity; identity không trả được thì dùng tên lưu sẵn trong phiên. */
    private PatientProfileDto patientOf(ConsultationSession s, Conversation conversation, Map<String, IdentityClient.ProfileDetail> profiles) {
        IdentityClient.ProfileDetail p = conversation == null ? null : profiles.get(conversation.patientProfileId);
        if (p == null) {
            return new PatientProfileDto(conversation == null ? "" : conversation.patientProfileId, s.patientName == null ? "Bệnh nhân" : s.patientName,
                    "", "male", "self", null, "", "");
        }
        return mapper.toPatient(p);
    }
}
