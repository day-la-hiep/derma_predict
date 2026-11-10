package vn.derma.consultation.controller;

import lombok.AllArgsConstructor;
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import jakarta.validation.Valid;
import vn.derma.consultation.common.ApiResponse;
import vn.derma.consultation.common.AppException;
import vn.derma.consultation.common.AuthenticatedUser;
import vn.derma.consultation.common.CurrentUser;
import vn.derma.consultation.dto.ConsultationDtos.ConsultationSessionOutput;
import vn.derma.consultation.dto.ConsultationDtos.DoctorReplyInput;
import vn.derma.consultation.dto.ConsultationDtos.RequestConsultationInput;
import vn.derma.consultation.dto.MessageDtos.MessageOutput;
import vn.derma.consultation.service.ConsultationService;
import vn.derma.consultation.service.PubSubStreams;

/** `/doctor/consultations/{id}/finalize*`, `finalize-reports`, `journey-graph` thuộc clinical (gateway route theo đường dẫn dài hơn trước). */
@RestController
@RequestMapping("/api/v1")
@AllArgsConstructor
public class ConsultationController {

    private final ConsultationService consultations;
    private final PubSubStreams pubSub;

    @PostMapping("/conversations/{conversationId}/request-consultation")
    @ResponseStatus(HttpStatus.ACCEPTED)
    ApiResponse<ConsultationSessionOutput> request(@CurrentUser AuthenticatedUser user, @PathVariable String conversationId,
            @Valid @RequestBody RequestConsultationInput body) {
        return new ApiResponse<>(consultations.requestConsultation(conversationId, user.id(), body.reason()));
    }

    @GetMapping("/doctor/consultations")
    ApiResponse<List<ConsultationSessionOutput>> list(@CurrentUser AuthenticatedUser user, @RequestParam(required = false) String status) {
        requireDoctor(user);
        return new ApiResponse<>(consultations.list(user.id(), status));
    }

    @GetMapping("/doctor/consultations/stream")
    SseEmitter stream(@CurrentUser AuthenticatedUser user) {
        requireDoctor(user);
        return pubSub.subscribe(PubSubStreams.DOCTOR_INBOX);
    }

    @GetMapping("/doctor/consultations/{sessionId}")
    ApiResponse<ConsultationSessionOutput> get(@CurrentUser AuthenticatedUser user, @PathVariable String sessionId) {
        requireDoctor(user);
        return new ApiResponse<>(consultations.get(sessionId, user.id()));
    }

    @PostMapping("/doctor/consultations/{sessionId}/accept")
    ApiResponse<ConsultationSessionOutput> accept(@CurrentUser AuthenticatedUser user, @PathVariable String sessionId) {
        requireDoctor(user);
        return new ApiResponse<>(consultations.accept(sessionId, user.id()));
    }

    @PostMapping("/doctor/consultations/{sessionId}/resolve")
    ApiResponse<ConsultationSessionOutput> resolve(@CurrentUser AuthenticatedUser user, @PathVariable String sessionId) {
        requireDoctor(user);
        return new ApiResponse<>(consultations.resolve(sessionId, user.id()));
    }

    @PostMapping("/doctor/consultations/{sessionId}/reply")
    ApiResponse<MessageOutput> reply(@CurrentUser AuthenticatedUser user, @PathVariable String sessionId, @Valid @RequestBody DoctorReplyInput body) {
        requireDoctor(user);
        return new ApiResponse<>(consultations.reply(sessionId, user.id(), body.content()));
    }

    private static void requireDoctor(AuthenticatedUser user) {
        if (!"doctor".equals(user.role())) {
            throw AppException.forbidden("Bạn không có quyền truy cập chức năng này (yêu cầu vai trò: doctor).");
        }
    }
}
