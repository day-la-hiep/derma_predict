package vn.derma.consultation.controller;

import lombok.AllArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import jakarta.validation.Valid;
import vn.derma.consultation.common.ApiResponse;
import vn.derma.consultation.common.AuthenticatedUser;
import vn.derma.consultation.common.CurrentUser;
import vn.derma.consultation.dto.VideoCallDtos.EndCallInput;
import vn.derma.consultation.dto.VideoCallDtos.IceConfigOutput;
import vn.derma.consultation.dto.VideoCallDtos.SignalInput;
import vn.derma.consultation.dto.VideoCallDtos.StartCallInput;
import vn.derma.consultation.dto.VideoCallDtos.VideoCallOutput;
import vn.derma.consultation.service.IceConfigBuilder;
import vn.derma.consultation.service.PubSubStreams;
import vn.derma.consultation.service.VideoCallService;

@RestController
@RequestMapping("/api/v1")
@AllArgsConstructor
public class VideoCallController {

    private final VideoCallService calls;
    private final IceConfigBuilder iceConfig;
    private final PubSubStreams pubSub;

    /** SSE dài hạn của riêng tài khoản: cuộc gọi đến, đổi trạng thái, signaling; nhận được ở mọi trang. */
    @GetMapping("/video-calls/stream")
    SseEmitter stream(@CurrentUser AuthenticatedUser user) {
        return pubSub.subscribe(PubSubStreams.userCallsChannel(user.id()));
    }

    @GetMapping("/video-calls/ice-config")
    ApiResponse<IceConfigOutput> getIceConfig(@CurrentUser AuthenticatedUser user) {
        return new ApiResponse<>(iceConfig.build(user.id()));
    }

    @PostMapping("/conversations/{conversationId}/video-calls")
    @ResponseStatus(HttpStatus.CREATED)
    ApiResponse<VideoCallOutput> start(@CurrentUser AuthenticatedUser user, @PathVariable String conversationId,
            @Valid @RequestBody(required = false) StartCallInput body) {
        return new ApiResponse<>(calls.start(conversationId, user.id(), body == null ? "audio" : body.mode()));
    }

    @PostMapping("/video-calls/{callId}/accept")
    ApiResponse<VideoCallOutput> accept(@CurrentUser AuthenticatedUser user, @PathVariable String callId) {
        return new ApiResponse<>(calls.accept(callId, user.id()));
    }

    @PostMapping("/video-calls/{callId}/end")
    ApiResponse<VideoCallOutput> end(@CurrentUser AuthenticatedUser user, @PathVariable String callId, @Valid @RequestBody(required = false) EndCallInput body) {
        return new ApiResponse<>(calls.end(callId, user.id(), body != null && "missed".equals(body.reason())));
    }

    @PostMapping("/video-calls/{callId}/signal")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    void signal(@CurrentUser AuthenticatedUser user, @PathVariable String callId, @Valid @RequestBody SignalInput body) {
        calls.signal(callId, user.id(), body.kind(), body.payload());
    }
}
