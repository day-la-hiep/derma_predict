package vn.derma.consultation.service;

import lombok.AllArgsConstructor;
import java.util.List;

import org.springframework.stereotype.Service;

import vn.derma.consultation.client.IdentityClient;
import vn.derma.consultation.common.AppException;
import vn.derma.consultation.config.DermaProperties;
import vn.derma.consultation.dto.ConversationDtos.ConversationOutput;
import vn.derma.consultation.dto.ConversationDtos.CreateConversationInput;
import vn.derma.consultation.dto.ConversationDtos.ModelOption;
import vn.derma.consultation.mapper.ConsultationMapper;
import vn.derma.consultation.entity.Conversation;
import vn.derma.consultation.repository.ConversationRepository;

@Service
@AllArgsConstructor
public class ConversationService {

    private final ConversationRepository conversations;
    private final IdentityClient identity;
    private final MessageService messages;
    private final DermaProperties properties;
    private final ConsultationMapper mapper;

    public List<ModelOption> listModels() {
        return properties.models().stream().map(ModelOption::new).toList();
    }

    public List<ConversationOutput> list(String userId) {
        return conversations.findByUserIdAndKindOrderByCreatedAtDesc(userId, "ai_chat").stream().map(mapper::toConversationOutput).toList();
    }

    public ConversationOutput create(String userId, CreateConversationInput input) {
        String model = input.model() == null ? properties.defaultModel() : checkModel(input.model());
        IdentityClient.ProfileRef profile = identity.resolveProfile(userId, input.patientProfileId())
                .orElseThrow(() -> AppException.badRequest("Không tìm thấy hồ sơ bệnh nhân của tài khoản."));
        Conversation conversation = new Conversation();
        conversation.userId = userId;
        conversation.patientProfileId = profile.id();
        conversation.title = input.title() == null ? "" : input.title();
        conversation.model = model;
        conversations.save(conversation);
        if (!input.content().isBlank()) {
            messages.startFirstTurn(conversation, input.content());
        }
        return mapper.toConversationOutput(conversation);
    }

    public ConversationOutput updateModel(String conversationId, String userId, String model) {
        Conversation conversation = conversations.findByIdAndUserId(conversationId, userId).orElseThrow(() -> AppException.notFound("hội thoại"));
        conversation.model = checkModel(model);
        return mapper.toConversationOutput(conversations.save(conversation));
    }

    private String checkModel(String model) {
        if (!properties.models().contains(model)) {
            throw AppException.invalid("model=\"" + model + "\" không hợp lệ — chỉ nhận: " + String.join(", ", properties.models()) + ".");
        }
        return model;
    }
}
