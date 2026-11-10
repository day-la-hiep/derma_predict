package vn.derma.consultation;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.List;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.junit.jupiter.api.Test;

import vn.derma.consultation.config.DermaProperties;
import vn.derma.consultation.dto.VideoCallDtos.IceConfigOutput;
import vn.derma.consultation.service.IceConfigBuilder;

class IceConfigBuilderTest {

    private IceConfigBuilder builder(String turnUrl, String meteredUser) {
        var webrtc = new DermaProperties.Webrtc(List.of("stun:s:1"), turnUrl, "bi-mat", 3600, "relay.example", meteredUser, meteredUser.isEmpty() ? "" : "mat-khau");
        return new IceConfigBuilder(new DermaProperties(null, null, null, null, null, null, 0, 0, null, webrtc));
    }

    @Test
    void turnCredentialIsHmacSha1OfUsernameLikeCoturnUseAuthSecret() throws Exception {
        IceConfigOutput out = builder("turn:host:3478", "").build("u1");
        assertEquals(2, out.iceServers().size());
        var turn = out.iceServers().get(1);
        assertTrue(turn.username().endsWith(":u1"));
        Mac mac = Mac.getInstance("HmacSHA1");
        mac.init(new SecretKeySpec("bi-mat".getBytes(StandardCharsets.UTF_8), "HmacSHA1"));
        assertEquals(Base64.getEncoder().encodeToString(mac.doFinal(turn.username().getBytes(StandardCharsets.UTF_8))), turn.credential());
        assertTrue(Long.parseLong(turn.username().split(":")[0]) > System.currentTimeMillis() / 1000);
    }

    @Test
    void stunOnlyWithoutTurnAndMeteredAddsRelayServers() {
        assertEquals(1, builder("", "").build("u1").iceServers().size());
        IceConfigOutput out = builder("", "nguoi-dung").build("u1");
        assertEquals(3, out.iceServers().size());
        assertEquals("nguoi-dung", out.iceServers().get(2).username());
        assertEquals("turns:relay.example:443?transport=tcp", out.iceServers().get(2).urls().get(3));
    }
}
