package vn.derma.consultation.dto;

import java.util.List;
import java.util.Map;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

public final class VideoCallDtos {

    private VideoCallDtos() {
    }

    /** `mode` chỉ để bên nhận biết bên gọi có bật camera; không lưu DB. */
    public record StartCallInput(@Pattern(regexp = "audio|video") String mode) {
    }

    /** `reason` = `missed`: bên gọi tự huỷ vì hết giờ không ai bắt máy. */
    public record EndCallInput(@Pattern(regexp = "missed") String reason) {
    }

    /** `kind` = offer | answer | candidate | media (bên kia bật/tắt mic, camera). */
    public record SignalInput(@NotBlank @Pattern(regexp = "offer|answer|candidate|media") String kind, @NotNull Map<String, Object> payload) {
    }

    public record VideoCallOutput(String id, String conversationId, String doctorId, String roomId, String status, String startedAt, String endedAt) {
    }

    public record IceServer(List<String> urls, String username, String credential) {
    }

    public record IceConfigOutput(List<IceServer> iceServers) {
    }
}
