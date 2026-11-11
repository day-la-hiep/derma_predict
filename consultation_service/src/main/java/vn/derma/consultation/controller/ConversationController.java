package vn.derma.consultation.controller;

import lombok.AllArgsConstructor;
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import jakarta.validation.Valid;
import vn.derma.consultation.common.ApiResponse;
import vn.derma.consultation.common.AuthenticatedUser;
import vn.derma.consultation.common.CurrentUser;
import vn.derma.consultation.dto.ConversationDtos.ConversationOutput;
import vn.derma.consultation.dto.ConversationDtos.CreateConversationInput;
import vn.derma.consultation.dto.ConversationDtos.ModelOption;
import vn.derma.consultation.dto.ConversationDtos.UpdateConversationModelInput;
import vn.derma.consultation.dto.MessageDtos.AnswerInput;
import vn.derma.consultation.dto.MessageDtos.MessageOutput;
import vn.derma.consultation.dto.MessageDtos.SendMessageInput;
import vn.derma.consultation.dto.MessageDtos.SendMessageResult;
import vn.derma.consultation.service.ConversationService;
import vn.derma.consultation.service.FollowupService;
import vn.derma.consultation.service.MessageService;

@RestController
@RequestMapping("/api/v1")
@AllArgsConstructor
public class ConversationController {

    private final ConversationService conversations;
    private final MessageService messages;
    private final FollowupService followups;

    @GetMapping("/models")
    ApiResponse<List<ModelOption>> listModels() {
        return new ApiResponse<>(conversations.listModels());
    }

    @GetMapping("/conversations")
    ApiResponse<List<ConversationOutput>> list(@CurrentUser AuthenticatedUser user) {
        return new ApiResponse<>(conversations.list(user.id()));
    }

    @PostMapping("/conversations")
    @ResponseStatus(HttpStatus.CREATED)
    ApiResponse<ConversationOutput> create(@CurrentUser AuthenticatedUser user, @Valid @RequestBody CreateConversationInput body) {
        return new ApiResponse<>(conversations.create(user.id(), body));
    }

    @PatchMapping("/conversations/{conversationId}/model")
    ApiResponse<ConversationOutput> updateModel(@CurrentUser AuthenticatedUser user, @PathVariable String conversationId,
            @Valid @RequestBody UpdateConversationModelInput body) {
        return new ApiResponse<>(conversations.updateModel(conversationId, user.id(), body.model()));
    }

    @GetMapping("/conversations/{conversationId}/messages")
    ApiResponse<List<MessageOutput>> listMessages(@CurrentUser AuthenticatedUser user, @PathVariable String conversationId) {
        followups.requireAccess(conversationId, user);
        return new ApiResponse<>(messages.listForRoom(conversationId));
    }

    @PostMapping("/conversations/{conversationId}/messages")
    @ResponseStatus(HttpStatus.ACCEPTED)
    ApiResponse<SendMessageResult> sendMessage(@CurrentUser AuthenticatedUser user, @PathVariable String conversationId,
            @Valid @RequestBody SendMessageInput body) {
        return new ApiResponse<>(messages.send(conversationId, user, body));
    }

    @PostMapping("/conversations/{conversationId}/questions/{questionId}/answer")
    @ResponseStatus(HttpStatus.ACCEPTED)
    ApiResponse<MessageOutput> answerQuestion(@CurrentUser AuthenticatedUser user, @PathVariable String conversationId,
            @PathVariable String questionId, @Valid @RequestBody AnswerInput body) {
        return new ApiResponse<>(messages.answerQuestion(conversationId, user.id(), questionId, body));
    }

    @PostMapping("/conversations/{conversationId}/cancel")
    @ResponseStatus(HttpStatus.ACCEPTED)
    ApiResponse<Void> cancel(@CurrentUser AuthenticatedUser user, @PathVariable String conversationId) {
        messages.cancel(conversationId, user.id());
        return new ApiResponse<>(null);
    }
}
