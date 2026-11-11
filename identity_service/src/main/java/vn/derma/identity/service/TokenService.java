package vn.derma.identity.service;

import java.nio.charset.StandardCharsets;
import java.text.ParseException;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;
import java.util.UUID;

import org.springframework.stereotype.Service;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.MACSigner;
import com.nimbusds.jose.crypto.MACVerifier;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import vn.derma.identity.common.AppException;
import vn.derma.identity.config.DermaProperties;

/** JWT HS256 cùng khoá/claim với `core/` (xem services/contracts/README.md mục 2) để service Python verify được. */
@Service
public class TokenService {

    public record Claims(String userId, String role, String type, String jti) {
    }

    public record RefreshToken(String token, String jti, Duration ttl) {
    }

    private final byte[] secret;
    private final DermaProperties.Jwt config;

    public TokenService(DermaProperties properties) {
        this.config = properties.jwt();
        this.secret = config.secret().getBytes(StandardCharsets.UTF_8);
    }

    public String createAccessToken(String userId, String username, String role) {
        Instant now = Instant.now();
        return sign(new JWTClaimsSet.Builder()
                .subject(userId)
                .claim("username", username)
                .claim("role", role)
                .claim("type", "access")
                .issueTime(Date.from(now))
                .expirationTime(Date.from(now.plus(Duration.ofMinutes(config.accessTokenMinutes()))))
                .build());
    }

    public RefreshToken createRefreshToken(String userId) {
        Instant now = Instant.now();
        Duration ttl = Duration.ofDays(config.refreshTokenDays());
        String jti = UUID.randomUUID().toString();
        String token = sign(new JWTClaimsSet.Builder()
                .subject(userId)
                .jwtID(jti)
                .claim("type", "refresh")
                .issueTime(Date.from(now))
                .expirationTime(Date.from(now.plus(ttl)))
                .build());
        return new RefreshToken(token, jti, ttl);
    }

    /** Ném 401 nếu chữ ký sai hoặc token hết hạn. */
    public Claims parse(String token) {
        try {
            SignedJWT jwt = SignedJWT.parse(token);
            JWTClaimsSet claims = jwt.getJWTClaimsSet();
            boolean expired = claims.getExpirationTime() == null || claims.getExpirationTime().before(new Date());
            if (!jwt.verify(new MACVerifier(secret)) || expired) {
                throw AppException.unauthorized("Token không hợp lệ hoặc đã hết hạn.");
            }
            return new Claims(claims.getSubject(), (String) claims.getClaim("role"), (String) claims.getClaim("type"), claims.getJWTID());
        } catch (ParseException | JOSEException e) {
            throw AppException.unauthorized("Token không hợp lệ hoặc đã hết hạn.");
        }
    }

    private String sign(JWTClaimsSet claims) {
        try {
            SignedJWT jwt = new SignedJWT(new JWSHeader(JWSAlgorithm.HS256), claims);
            jwt.sign(new MACSigner(secret));
            return jwt.serialize();
        } catch (JOSEException e) {
            throw new IllegalStateException("Không ký được JWT", e);
        }
    }
}
