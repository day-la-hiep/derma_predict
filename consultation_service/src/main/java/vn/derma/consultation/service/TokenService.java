package vn.derma.consultation.service;

import java.nio.charset.StandardCharsets;
import java.text.ParseException;
import java.util.Date;

import org.springframework.stereotype.Service;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.crypto.MACVerifier;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import vn.derma.consultation.common.AppException;
import vn.derma.consultation.config.DermaProperties;

/** Chỉ verify JWT HS256 do identity phát (cùng khoá, claim `sub`/`role`/`type`); consultation không phát token. */
@Service
public class TokenService {

    public record Claims(String userId, String role, String type) {
    }

    private final byte[] secret;

    public TokenService(DermaProperties properties) {
        this.secret = properties.jwt().secret().getBytes(StandardCharsets.UTF_8);
    }

    public Claims parse(String token) {
        try {
            SignedJWT jwt = SignedJWT.parse(token);
            JWTClaimsSet claims = jwt.getJWTClaimsSet();
            boolean expired = claims.getExpirationTime() == null || claims.getExpirationTime().before(new Date());
            if (!jwt.verify(new MACVerifier(secret)) || expired) {
                throw AppException.unauthorized("Token không hợp lệ hoặc đã hết hạn.");
            }
            return new Claims(claims.getSubject(), (String) claims.getClaim("role"), (String) claims.getClaim("type"));
        } catch (ParseException | JOSEException e) {
            throw AppException.unauthorized("Token không hợp lệ hoặc đã hết hạn.");
        }
    }
}
