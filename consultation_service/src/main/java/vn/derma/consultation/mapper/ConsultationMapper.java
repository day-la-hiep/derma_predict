package vn.derma.consultation.mapper;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

import vn.derma.consultation.dto.MessageDtos.ConversationInfo;
import vn.derma.consultation.dto.MessageDtos.HistoryItem;
import vn.derma.consultation.dto.ConversationDtos.ConversationOutput;
import vn.derma.consultation.dto.VideoCallDtos.VideoCallOutput;
import vn.derma.consultation.entity.Conversation;
import vn.derma.consultation.dto.MessageDtos.FileDto;
import vn.derma.consultation.dto.MessageDtos.MessageInfo;
import vn.derma.consultation.dto.MessageDtos.MessageOutput;
import vn.derma.consultation.entity.Message;
import vn.derma.consultation.entity.StoredFile;
import vn.derma.consultation.entity.VideoCall;

/** Entity → DTO. */
@Mapper
public interface ConsultationMapper {

    ConversationOutput toConversationOutput(Conversation conversation);

    @Mapping(target = "id", source = "call.id")
    @Mapping(target = "conversationId", source = "conversation.id")
    @Mapping(target = "doctorId", source = "conversation.doctorId")
    @Mapping(target = "roomId", source = "call.roomId")
    @Mapping(target = "status", source = "call.status")
    @Mapping(target = "startedAt", source = "call.startedAt")
    @Mapping(target = "endedAt", source = "call.endedAt")
    VideoCallOutput toVideoCallOutput(VideoCall call, Conversation conversation);

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

    default String toText(Instant value) {
        return value == null ? null : value.toString();
    }
}
