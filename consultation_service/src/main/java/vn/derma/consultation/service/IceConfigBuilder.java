package vn.derma.consultation.service;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.springframework.stereotype.Component;

import vn.derma.consultation.config.DermaProperties;
import vn.derma.consultation.dto.VideoCallDtos.IceConfigOutput;
import vn.derma.consultation.dto.VideoCallDtos.IceServer;

/** Danh sách STUN/TURN cho WebRTC; TURN dùng credential tạm theo coturn `use-auth-secret`. */
@Component
public class IceConfigBuilder {

    private final DermaProperties.Webrtc config;

    public IceConfigBuilder(DermaProperties properties) {
        this.config = properties.webrtc();
    }

    public IceConfigOutput build(String userId) {
        List<IceServer> servers = new ArrayList<>();
        servers.add(new IceServer(config.stunUrls(), null, null));
        if (config.turnUrl() != null && !config.turnUrl().isBlank()) {
            // username = "<hết hạn>:<user>", credential = base64(HMAC-SHA1(secret, username))
            String username = (Instant.now().getEpochSecond() + config.turnCredentialTtlSeconds()) + ":" + userId;
            servers.add(new IceServer(List.of(config.turnUrl()), username, hmacSha1(config.turnSecret(), username)));
        }
        if (notBlank(config.meteredUsername()) && notBlank(config.meteredCredential())) {
            String host = config.meteredHost();
            // cổng 80/443 + TCP/TLS để vượt firewall chặn UDP
            servers.add(new IceServer(List.of("stun:stun.relay.metered.ca:80"), null, null));
            servers.add(new IceServer(List.of("turn:" + host + ":80", "turn:" + host + ":80?transport=tcp", "turn:" + host + ":443",
                    "turns:" + host + ":443?transport=tcp"), config.meteredUsername(), config.meteredCredential()));
        }
        return new IceConfigOutput(servers);
    }

    private static boolean notBlank(String value) {
        return value != null && !value.isBlank();
    }

    private static String hmacSha1(String secret, String data) {
        try {
            Mac mac = Mac.getInstance("HmacSHA1");
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA1"));
            return Base64.getEncoder().encodeToString(mac.doFinal(data.getBytes(StandardCharsets.UTF_8)));
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("Không tạo được credential TURN", e);
        }
    }
}
