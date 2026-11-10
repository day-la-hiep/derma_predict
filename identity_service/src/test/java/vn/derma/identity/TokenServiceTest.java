package vn.derma.identity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

import vn.derma.identity.common.AppException;
import vn.derma.identity.config.DermaProperties;
import vn.derma.identity.service.TokenService;

/** Token và hash mẫu sinh bằng `core/app/config/security.py` để chắc hai bên đọc được của nhau. */
class TokenServiceTest {

    private static final String PYTHON_ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyLTkiLCJ1c2VybmFtZSI6ImJzLmFuIiwicm9sZSI6ImRvY3RvciIsInR5cGUiOiJhY2Nlc3MiLCJpYXQiOjE3OTQyMzcwODAsImV4cCI6NDk0NzgzNzA4MH0.vqR2ZlXy0VsDTdpldPOwiUqZMx-A68jtKigejiC-H4Q";
    private static final String PYTHON_BCRYPT_HASH = "$2b$12$yWxxBbYO5JR74ixafuCIjexvZj5MpgwfpXq9epqwU1OZbxp7Z7Gp2";
    private static final String SECRET = "derma-secret-key-change-in-production-datn-2026";

    private TokenService serviceWith(String secret, int accessMinutes) {
        return new TokenService(new DermaProperties(new DermaProperties.Jwt(secret, accessMinutes, 30), "k", "", ""));
    }

    @Test
    void readsAccessTokenIssuedByPython() {
        TokenService.Claims claims = serviceWith(SECRET, 30).parse(PYTHON_ACCESS_TOKEN);
        assertEquals("user-9", claims.userId());
        assertEquals("doctor", claims.role());
        assertEquals("access", claims.type());
    }

    @Test
    void roundTripsAccessAndRefreshTokens() {
        TokenService tokens = serviceWith(SECRET, 30);
        TokenService.Claims access = tokens.parse(tokens.createAccessToken("u1", "an", "admin"));
        assertEquals("u1", access.userId());
        assertEquals("admin", access.role());
        TokenService.RefreshToken refresh = tokens.createRefreshToken("u1");
        TokenService.Claims claims = tokens.parse(refresh.token());
        assertEquals("refresh", claims.type());
        assertEquals(refresh.jti(), claims.jti());
    }

    @Test
    void rejectsWrongKeyAndExpiredToken() {
        TokenService other = serviceWith("khoa-khac-khoa-khac-khoa-khac-khoa-khac-12345", 30);
        assertThrows(AppException.class, () -> serviceWith(SECRET, 30).parse(other.createAccessToken("u1", "an", "admin")));
        TokenService expired = serviceWith(SECRET, -1);
        assertThrows(AppException.class, () -> serviceWith(SECRET, 30).parse(expired.createAccessToken("u1", "an", "admin")));
        assertThrows(AppException.class, () -> serviceWith(SECRET, 30).parse("khong-phai-jwt"));
    }

    @Test
    void verifiesBcryptHashCreatedByPython() {
        BCryptPasswordEncoder encoder = new BCryptPasswordEncoder();
        assertEquals(true, encoder.matches("matkhau123", PYTHON_BCRYPT_HASH));
        assertEquals(false, encoder.matches("sai", PYTHON_BCRYPT_HASH));
    }
}
