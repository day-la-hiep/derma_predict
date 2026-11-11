package vn.derma.consultation.service;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import lombok.AllArgsConstructor;
import vn.derma.consultation.client.IdentityClient;
import vn.derma.consultation.common.AppException;
import vn.derma.consultation.common.AuthenticatedUser;
import vn.derma.consultation.config.DermaProperties;
import vn.derma.consultation.dto.FollowupDtos.FollowupChannelOutput;
import vn.derma.consultation.entity.Conversation;
import vn.derma.consultation.entity.Message;
import vn.derma.consultation.repository.ConversationRepository;
import vn.derma.consultation.repository.MessageRepository;

/** Kênh chat bác sĩ ↔ bệnh nhân sau khám: một hội thoại `doctor_followup` cho mỗi lần khám, AI không tham gia. */
@Service
@AllArgsConstructor
public class FollowupService {

    public static final String AI_CHAT = "ai_chat";
    public static final String FOLLOWUP = "doctor_followup";
    private static final int DEFAULT_EXTEND_DAYS = 30;

    private final ConversationRepository conversations;
    private final MessageRepository messages;
    private final IdentityClient identity;
    private final DermaProperties properties;

    /** Hội thoại AI chỉ chủ sở hữu xem; kênh theo dõi thì bệnh nhân chủ kênh và bác sĩ của kênh. */
    public Conversation requireAccess(String conversationId, AuthenticatedUser user) {
        Conversation conversation = conversations.findById(conversationId).orElseThrow(() -> AppException.notFound("hội thoại"));
        if (!conversation.userId.equals(user.id()) && !(FOLLOWUP.equals(conversation.kind) && user.id().equals(conversation.doctorId))) {
            throw AppException.forbidden("Bạn không có quyền xem hội thoại này.");
        }
        return conversation;
    }

    public static boolean isOpen(Conversation channel) {
        return channel.followupUntil == null || channel.followupUntil.isAfter(Instant.now());
    }

    /** clinical gọi khi bắt đầu khám; gọi lại cho cùng lần khám thì trả kênh đã có. */
    @Transactional
    public String createChannel(String encounterId, String patientProfileId, String doctorId) {
        return conversations.findByEncounterId(encounterId).map(c -> c.id).orElseGet(() -> {
            IdentityClient.ProfileDetail profile = identity.getProfiles(Set.of(patientProfileId)).get(patientProfileId);
            if (profile == null) {
                throw AppException.badRequest("Không tìm thấy hồ sơ bệnh nhân " + patientProfileId + " để mở kênh theo dõi.");
            }
            Conversation channel = new Conversation();
            channel.userId = profile.userId();
            channel.patientProfileId = patientProfileId;
            channel.title = "Theo dõi sau khám";
            channel.model = properties.defaultModel();
            channel.kind = FOLLOWUP;
            channel.encounterId = encounterId;
            channel.doctorId = doctorId;
            return conversations.save(channel).id;
        });
    }

    @Transactional
    public void setUntil(String encounterId, Instant until) {
        Conversation channel = conversations.findByEncounterId(encounterId).orElseThrow(() -> AppException.notFound("kênh theo dõi của lần khám " + encounterId));
        channel.followupUntil = until;
        conversations.save(channel);
    }

    public FollowupChannelOutput getByEncounter(String encounterId, AuthenticatedUser user) {
        Conversation channel = conversations.findByEncounterId(encounterId).orElseThrow(() -> AppException.notFound("kênh theo dõi"));
        requireAccess(channel.id, user);
        return outputs(List.of(channel)).get(0);
    }

    public List<FollowupChannelOutput> listForDoctor(String doctorId) {
        return outputs(conversations.findByDoctorIdAndKindOrderByUpdatedAtDesc(doctorId, FOLLOWUP));
    }

    @Transactional
    public FollowupChannelOutput extend(String conversationId, String doctorId, Integer days) {
        Conversation channel = conversations.findById(conversationId).filter(c -> FOLLOWUP.equals(c.kind) && doctorId.equals(c.doctorId))
                .orElseThrow(() -> AppException.notFound("kênh theo dõi"));
        if (channel.followupUntil == null) {
            throw AppException.conflict("Lần khám chưa chốt kết luận nên kênh chưa có hạn để gia hạn.");
        }
        if (!isOpen(channel)) {
            throw AppException.conflict("Kênh đã hết hạn, chỉ còn đọc; tái khám sẽ mở kênh mới.");
        }
        channel.followupUntil = channel.followupUntil.plus(Duration.ofDays(days == null ? DEFAULT_EXTEND_DAYS : days));
        conversations.save(channel);
        return outputs(List.of(channel)).get(0);
    }

    private List<FollowupChannelOutput> outputs(List<Conversation> found) {
        Map<String, IdentityClient.ProfileDetail> profiles = identity.getProfiles(found.stream().map(c -> c.patientProfileId).collect(Collectors.toSet()));
        Map<String, String> doctorNames = found.stream().map(c -> c.doctorId).filter(java.util.Objects::nonNull).distinct()
                .collect(Collectors.toMap(id -> id, id -> identity.getUser(id).map(IdentityClient.UserRef::fullName).orElse("Bác sĩ")));
        return found.stream().map(c -> {
            IdentityClient.ProfileDetail patient = profiles.get(c.patientProfileId);
            Message last = messages.findFirstByConversationIdOrderByCreatedAtDesc(c.id).orElse(null);
            return new FollowupChannelOutput(c.id, c.encounterId, isOpen(c) ? "open" : "read_only",
                    c.followupUntil == null ? null : c.followupUntil.toString(), c.doctorId, doctorNames.get(c.doctorId),
                    c.patientProfileId, patient == null ? null : patient.fullName(),
                    last == null ? null : last.createdAt.toString(),
                    last == null ? null : last.content.length() > 80 ? last.content.substring(0, 80) : last.content);
        }).toList();
    }
}
