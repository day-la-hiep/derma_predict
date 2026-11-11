package vn.derma.identity.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "derma")
public record DermaProperties(Jwt jwt, String internalApiKey, String clinicalUrl, String consultationUrl) {

    public record Jwt(String secret, int accessTokenMinutes, int refreshTokenDays) {
    }
}
