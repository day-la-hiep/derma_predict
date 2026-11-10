package vn.derma.consultation.mapper;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

import vn.derma.consultation.dto.ConsultationDtos.ConsultationSessionOutput;
import vn.derma.consultation.dto.ConsultationDtos.PatientProfileDto;
import vn.derma.consultation.dto.ConsultationDtos.PreConsultationReportOutput;
import vn.derma.consultation.client.IdentityClient.ProfileDetail;
import vn.derma.consultation.dto.MessageDtos.ConversationInfo;
import vn.derma.consultation.dto.MessageDtos.HistoryItem;
import vn.derma.consultation.dto.ConversationDtos.ConversationOutput;
import vn.derma.consultation.dto.VideoCallDtos.VideoCallOutput;
import vn.derma.consultation.entity.ConsultationSession;
import vn.derma.consultation.entity.Conversation;
import vn.derma.consultation.dto.MessageDtos.FileDto;
import vn.derma.consultation.dto.MessageDtos.MessageInfo;
import vn.derma.consultation.dto.MessageDtos.MessageOutput;
import vn.derma.consultation.entity.Message;
import vn.derma.consultation.entity.PreConsultationReport;
import vn.derma.consultation.entity.StoredFile;
import vn.derma.consultation.entity.VideoCall;

/** Entity → DTO; tên hội thoại, bệnh nhân và báo cáo do service ghép từ nhiều nơi rồi truyền vào. */
@Mapper
public interface ConsultationMapper {

    ConversationOutput toConversationOutput(Conversation conversation);

    PreConsultationReportOutput toReportOutput(PreConsultationReport report);

    @Mapping(target = "id", source = "call.id")
    @Mapping(target = "conversationId", source = "session.conversationId")
    @Mapping(target = "doctorId", source = "session.doctorId")
    @Mapping(target = "roomId", source = "call.roomId")
    @Mapping(target = "status", source = "call.status")
    @Mapping(target = "startedAt", source = "call.startedAt")
    @Mapping(target = "endedAt", source = "call.endedAt")
    VideoCallOutput toVideoCallOutput(VideoCall call, ConsultationSession session);

    @Mapping(target = "id", source = "session.id")
    @Mapping(target = "conversationId", source = "session.conversationId")
    @Mapping(target = "doctorId", source = "session.doctorId")
    @Mapping(target = "status", source = "session.status")
    @Mapping(target = "reason", source = "session.reason", defaultValue = "Bệnh nhân yêu cầu bác sĩ tư vấn")
    @Mapping(target = "requestedAt", source = "session.requestedAt")
    @Mapping(target = "startedAt", source = "session.startedAt")
    @Mapping(target = "resolvedAt", source = "session.resolvedAt")
    @Mapping(target = "conversationTitle", source = "conversationTitle")
    @Mapping(target = "patient", source = "patient")
    @Mapping(target = "report", source = "report")
    @Mapping(target = "clinicalFacts", expression = "java(java.util.List.of())")
    ConsultationSessionOutput toSessionOutput(ConsultationSession session, String conversationTitle, PatientProfileDto patient, PreConsultationReportOutput report);

    @Mapping(target = "id", source = "message.id")
    @Mapping(target = "conversationId", source = "message.conversationId")
    @Mapping(target = "sender", source = "message.sender")
    @Mapping(target = "content", source = "message.content")
    @Mapping(target = "status", source = "message.status")
    @Mapping(target = "createdAt", source = "message.createdAt")
    @Mapping(target = "metadata", source = "metadata")
    MessageOutput toMessageOutput(Message message, Map<String, Object> metadata);

    @Mapping(target = "id", source = "message.id")
    @Mapping(target = "conversationId", source = "message.conversationId")
    @Mapping(target = "sender", source = "message.sender")
    @Mapping(target = "content", source = "message.content")
    @Mapping(target = "createdAt", source = "message.createdAt")
    @Mapping(target = "files", source = "files")
    MessageInfo toMessageInfo(Message message, List<FileDto> files);

    @Mapping(target = "fileName", source = "file.fileName")
    @Mapping(target = "storageKey", source = "file.storageKey")
    @Mapping(target = "contentType", source = "file.contentType")
    @Mapping(target = "size", source = "file.size")
    @Mapping(target = "createdAt", source = "file.createdAt")
    @Mapping(target = "url", source = "url")
    FileDto toFileDto(StoredFile file, String url);

    ConversationInfo toConversationInfo(Conversation conversation);

    HistoryItem toHistoryItem(Message message);

    @Mapping(target = "allergies", constant = "")
    @Mapping(target = "medicalHistory", constant = "")
    PatientProfileDto toPatient(ProfileDetail profile);

    default String toText(Instant value) {
        return value == null ? null : value.toString();
    }
}
