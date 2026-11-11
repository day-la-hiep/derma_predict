package vn.derma.consultation.service;

import lombok.AllArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;
import vn.derma.consultation.client.AiClient;
import vn.derma.consultation.common.AppException;
import vn.derma.consultation.common.AuthenticatedUser;
import vn.derma.consultation.config.DermaProperties;
import vn.derma.consultation.dto.MessageDtos.AnswerInput;
import vn.derma.consultation.dto.MessageDtos.AttachedFile;
import vn.derma.consultation.dto.MessageDtos.FileDto;
import vn.derma.consultation.dto.MessageDtos.HistoryItem;
import vn.derma.consultation.dto.MessageDtos.MessageOutput;
import vn.derma.consultation.dto.MessageDtos.SendMessageInput;
import vn.derma.consultation.dto.MessageDtos.SendMessageResult;
import vn.derma.consultation.dto.MessageDtos.TurnResultInput;
import vn.derma.consultation.mapper.ConsultationMapper;
import vn.derma.consultation.entity.Conversation;
import vn.derma.consultation.entity.Message;
import vn.derma.consultation.entity.MessageFile;
import vn.derma.consultation.entity.StoredFile;
import vn.derma.consultation.entity.VideoCall;
import vn.derma.consultation.repository.ConversationRepository;
import vn.derma.consultation.repository.MessageFileRepository;
import vn.derma.consultation.repository.MessageRepository;
import vn.derma.consultation.repository.StoredFileRepository;
import vn.derma.consultation.repository.VideoCallRepository;

@Service
@Slf4j
@AllArgsConstructor
public class MessageService {

    private record Turn(Message user, Message assistant, List<StoredFile> files) {
    }

    /** Lượt AI đang chạy hoặc đang chờ người dùng trả lời `ask_user`. */
    private static final Set<String> ACTIVE_TURN = Set.of("queued", "streaming", "question");
    private static final String ERROR_TEXT = "Xin lỗi, hệ thống gặp sự cố khi xử lý câu hỏi này (có thể do quá tải tạm thời). Vui lòng thử lại sau ít phút.";
    private static final TypeReference<Map<String, Object>> MAP_TYPE = new TypeReference<>() {
    };

    private final MessageRepository messages;
    private final ConversationRepository conversations;
        private final AiClient ai;
    private final ConversationEvents events;
    private final ObjectMapper json;
    private final TransactionTemplate tx;
    private final DermaProperties properties;
    private final StoredFileRepository files;
    private final MessageFileRepository links;
    private final AttachmentStore store;
    private final VideoCallRepository videoCalls;
    private final ConsultationMapper mapper;

    /** Quyền xem đã kiểm ở `FollowupService.requireAccess`. */
    public List<MessageOutput> listForRoom(String conversationId) {
        List<Message> all = messages.findByConversationIdOrderByCreatedAtAsc(conversationId);
        Map<String, List<StoredFile>> attached = attachedFilesOf(all);
        Map<String, VideoCall> calls = new HashMap<>();
        videoCalls.findAllById(all.stream().map(m -> m.videoCallId).filter(java.util.Objects::nonNull).distinct().toList()).forEach(c -> calls.put(c.id, c));
        return all.stream().map(m -> toOutput(m, attached.get(m.id), m.videoCallId == null ? null : calls.get(m.videoCallId))).toList();
    }

    public SendMessageResult send(String conversationId, AuthenticatedUser user, SendMessageInput input) {
        Conversation conversation = conversations.findById(conversationId).orElseThrow(() -> AppException.notFound("hội thoại"));
        if (FollowupService.FOLLOWUP.equals(conversation.kind)) {
            return sendFollowup(conversation, user, input);
        }
        if (!conversation.userId.equals(user.id())) {
            throw AppException.notFound("hội thoại");
        }
        List<StoredFile> attachments = resolveAttachments(input.attachedFiles());
        if (messages.existsByConversationIdAndSenderAndStatusIn(conversationId, "ai", ACTIVE_TURN)) {
            throw AppException.conflict("Trợ lý đang trả lời hoặc đang chờ bạn trả lời câu hỏi, vui lòng đợi.");
        }
        if (input.modelId() != null && properties.models().contains(input.modelId()) && !input.modelId().equals(conversation.model)) {
            conversation.model = input.modelId();
            conversations.save(conversation);
        }
        Turn turn = openTurn(conversationId, input.content(), attachments);
        announce(turn.user(), attachments);
        dispatch(new AiClient.TurnRequest("turn", conversationId, turn.assistant().id, turn.user().id, input.clientMessageId(), input.content(),
                null, imagesForAi(attachments)));
        return new SendMessageResult(toOutput(turn.user(), attachments), toOutput(messages.findById(turn.assistant().id).orElse(turn.assistant())));
    }

    /** Kênh theo dõi: chỉ ghi DB và báo qua stream, AI không trả lời; quá hạn thì chỉ đọc. */
    private SendMessageResult sendFollowup(Conversation channel, AuthenticatedUser user, SendMessageInput input) {
        String sender = user.id().equals(channel.userId) ? "patient" : user.id().equals(channel.doctorId) ? "doctor" : null;
        if (sender == null) {
            throw AppException.notFound("hội thoại");
        }
        if (!FollowupService.isOpen(channel)) {
            throw AppException.conflict("Kênh theo dõi đã hết hạn, chỉ còn đọc. Vui lòng đặt lịch tái khám.");
        }
        List<StoredFile> attachments = resolveAttachments(input.attachedFiles());
        Message saved = saveUserMessage(channel.id, sender, input.content(), attachments).user();
        announce(saved, attachments);
        return new SendMessageResult(toOutput(saved, attachments), null);
    }

    /** Lượt đầu của hội thoại vừa tạo (có nội dung). */
    public void startFirstTurn(Conversation conversation, String content) {
        Turn turn = openTurn(conversation.id, content, List.of());
        announce(turn.user(), List.of());
        dispatch(new AiClient.TurnRequest("turn", conversation.id, turn.assistant().id, turn.user().id, null, content, null, null));
    }

    public MessageOutput answerQuestion(String conversationId, String userId, String questionId, AnswerInput input) {
        getOwned(conversationId, userId);
        Message pending = messages.findFirstByConversationIdAndSenderAndStatusOrderByCreatedAtDesc(conversationId, "ai", "question")
                .filter(m -> questionId.equals(readMetadata(m).getOrDefault("choice", Map.of()) instanceof Map<?, ?> c ? c.get("question_id") : null))
                .orElseThrow(() -> AppException.notFound("câu hỏi đang chờ trả lời"));
        dispatch(new AiClient.TurnRequest("resume", conversationId, pending.id, null, null, null, input.label(), null));
        return toOutput(pending);
    }

    public void cancel(String conversationId, String userId) {
        getOwned(conversationId, userId);
        Optional<Message> active = messages.findFirstByConversationIdAndSenderAndStatusInOrderByCreatedAtDesc(conversationId, "ai", ACTIVE_TURN);
        if (active.isEmpty()) {
            return;
        }
        boolean cancelled;
        try {
            cancelled = ai.cancelTurn(active.get().id);
        } catch (RuntimeException e) {
            log.warn("Không gọi được ai để dừng lượt {}; tự đóng tin nhắn", active.get().id, e);
            cancelled = false;
        }
        // ai không giữ lượt này (chưa chạy, hoặc ai đã khởi động lại): tự đóng để người dùng không bị kẹt
        if (!cancelled) {
            closeWithText(active.get(), "");
        }
    }

    /** ai gửi kết quả cuối của lượt: thay toàn bộ `metadata` (reasoning/choice) bằng bản mới nhất. */
    public void applyTurnResult(String messageId, TurnResultInput input) {
        Message message = messages.findById(messageId).orElseThrow(() -> AppException.notFound("tin nhắn " + messageId));
        Map<String, Object> metadata = new HashMap<>();
        if (input.reasoning() != null && !input.reasoning().isEmpty()) {
            metadata.put("reasoning", input.reasoning());
        }
        if (input.choice() != null) {
            metadata.put("choice", input.choice());
        }
        message.content = input.content() == null ? "" : input.content();
        message.status = input.status();
        message.metadata = metadata.isEmpty() ? null : json.writeValueAsString(metadata);
        messages.save(message);
    }

    /** Lượt AI treo quá hạn (ai chết giữa chừng, không gửi kết quả về): đóng bằng câu báo lỗi để người dùng gửi được tin mới. Trả số tin đã đóng. */
    public int closeStaleTurns(java.time.Instant cutoff) {
        List<Message> stale = messages.findBySenderAndStatusInAndCreatedAtBefore("ai", Set.of("queued", "streaming"), cutoff);
        stale.forEach(m -> closeWithText(m, ERROR_TEXT));
        return stale.size();
    }

    /** Nội dung các tin theo id (id không tồn tại thì bỏ qua), kèm tệp đính kèm. */
    public List<vn.derma.consultation.dto.MessageDtos.MessageInfo> describe(List<String> ids) {
        List<Message> found = messages.findAllById(ids);
        Map<String, List<StoredFile>> attached = attachedFilesOf(found);
        return found.stream().map(m -> mapper.toMessageInfo(m, attached.getOrDefault(m.id, List.of()).stream().map(this::toFileDto).toList())).toList();
    }

    public List<HistoryItem> history(String conversationId) {
        return messages.findByConversationIdOrderByCreatedAtAsc(conversationId).stream()
                .map(mapper::toHistoryItem).toList();
    }

    public MessageOutput toOutput(Message m) {
        return toOutput(m, List.of());
    }

    public MessageOutput toOutput(Message m, List<StoredFile> attachedFiles) {
        return toOutput(m, attachedFiles, null);
    }

    public MessageOutput toOutput(Message m, List<StoredFile> attachedFiles, VideoCall call) {
        Map<String, Object> metadata = new HashMap<>(readMetadata(m));
        metadata.put("message_type", m.messageType);
        if (attachedFiles != null && !attachedFiles.isEmpty()) {
            metadata.put("attached_files", attachedFiles.stream().map(this::toFileDto).toList());
        }
        if (call != null) {
            Map<String, Object> info = new HashMap<>();
            info.put("room_id", call.roomId);
            info.put("status", call.status);
            info.put("started_at", call.startedAt == null ? null : call.startedAt.toString());
            info.put("ended_at", call.endedAt == null ? null : call.endedAt.toString());
            metadata.put("video_call", info);
        }
        return mapper.toMessageOutput(m, metadata);
    }

    private Conversation getOwned(String conversationId, String userId) {
        return conversations.findByIdAndUserId(conversationId, userId).orElseThrow(() -> AppException.notFound("hội thoại"));
    }

    private Turn saveUserMessage(String conversationId, String sender, String content, List<StoredFile> attachments) {
        Message m = new Message();
        m.conversationId = conversationId;
        m.sender = sender;
        m.messageType = attachments.isEmpty() ? "text" : "attached";
        m.content = content;
        m.status = "done";
        Message saved = messages.save(m);
        attachments.forEach(f -> {
            MessageFile link = new MessageFile();
            link.messageId = saved.id;
            link.fileId = f.id;
            links.save(link);
        });
        return new Turn(saved, null, attachments);
    }

    public FileDto toFileDto(StoredFile f) {
        return mapper.toFileDto(f, store.presignedUrl(f.storageKey));
    }

    private List<StoredFile> resolveAttachments(List<AttachedFile> requested) {
        if (requested == null || requested.isEmpty()) {
            return List.of();
        }
        List<String> keys = requested.stream().map(AttachedFile::storageKey).toList();
        Map<String, StoredFile> found = new LinkedHashMap<>();
        files.findByStorageKeyIn(keys).forEach(f -> found.put(f.storageKey, f));
        List<String> missing = keys.stream().filter(k -> !found.containsKey(k)).toList();
        if (!missing.isEmpty()) {
            throw AppException.badRequest("Tệp đính kèm chưa được tải lên: " + String.join(", ", missing));
        }
        return keys.stream().map(found::get).toList();
    }

    private Map<String, List<StoredFile>> attachedFilesOf(List<Message> all) {
        if (all.isEmpty()) {
            return Map.of();
        }
        Map<String, StoredFile> byId = new HashMap<>();
        List<MessageFile> relations = links.findByMessageIdIn(all.stream().map(m -> m.id).toList());
        files.findAllById(relations.stream().map(r -> r.fileId).distinct().toList()).forEach(f -> byId.put(f.id, f));
        Map<String, List<StoredFile>> out = new HashMap<>();
        relations.forEach(r -> out.computeIfAbsent(r.messageId, k -> new java.util.ArrayList<>()).add(byId.get(r.fileId)));
        return out;
    }

    /** Chỉ chuyển ảnh sang ai (phân loại da); tệp khác ai không dùng. */
    private List<AiClient.AttachmentRef> imagesForAi(List<StoredFile> attachments) {
        List<AiClient.AttachmentRef> images = attachments.stream().filter(f -> f.contentType != null && f.contentType.startsWith("image/"))
                .map(f -> new AiClient.AttachmentRef(f.fileName, f.contentType, f.storageKey)).toList();
        return images.isEmpty() ? null : images;
    }

    private Turn openTurn(String conversationId, String content, List<StoredFile> attachments) {
        return tx.execute(status -> {
            Message user = saveUserMessage(conversationId, "patient", content, attachments).user();
            Message assistant = new Message();
            assistant.conversationId = conversationId;
            assistant.sender = "ai";
            assistant.status = "queued";
            assistant.metadata = "{\"reasoning\":[]}";
            return new Turn(user, messages.save(assistant), attachments);
        });
    }

    /** Gửi lượt sang ai sau khi DB đã commit; ai không nhận được thì đóng tin nhắn bằng thông báo lỗi để FE không chờ mãi. */
    private void dispatch(AiClient.TurnRequest request) {
        try {
            ai.startTurn(request);
        } catch (RuntimeException e) {
            log.error("Không gửi được lượt {} sang ai", request.messageId(), e);
            messages.findById(request.messageId()).ifPresent(m -> closeWithText(m, ERROR_TEXT));
        }
    }

    private void closeWithText(Message message, String content) {
        message.content = content;
        message.status = "done";
        messages.save(message);
        events.publish(message.conversationId, Map.of("type", "message.done", "conversation_id", message.conversationId,
                "message_id", message.id, "content", content));
    }

    private void announce(Message message, List<StoredFile> attachments) {
        events.publish(message.conversationId, Map.of("type", "message.created", "message", toOutput(message, attachments)));
    }

    private Map<String, Object> readMetadata(Message m) {
        return m.metadata == null || m.metadata.isBlank() ? Map.of() : json.readValue(m.metadata, MAP_TYPE);
    }
}
